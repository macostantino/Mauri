"""
Lectura de "Plantillas Echadas FullColor" (.xlsx).

El Excel es la ÚNICA fuente de verdad: no se recalcula ninguna echada.
Se leen literalmente:
  * la hoja "Indice reacom." (totales, combinaciones, tiradas y folio de plantilla),
  * cada hoja-plantilla: celdas (valores, fuentes, rellenos, bordes, combinaciones),
    geometría (anchos de columna / altos de fila) y las figuras dibujadas
    (óvalos, triángulos, rectángulos redondeados, heptágonos...) con su texto.

A partir de eso se detecta la estructura de taller de cada pliego
(encabezados ALTO/BAJO, marcas F/A, LADO 10 / LADO 13, posiciones de página)
solo para los listados estructurados; el dibujo reproduce la hoja tal cual.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

from .colors import drawingml_color, load_theme, openpyxl_color

EMU_PX = 9525  # EMU por píxel a 96 dpi
PARSER_VERSION = "2"

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

INDEX_SHEET_HINT = "indice"
KEYWORDS = {"ALTO", "BAJO"}
MARKS = {"F", "A"}

GEOM_ES = {
    "ellipse": "Óvalo",
    "triangle": "Triángulo",
    "roundRect": "Rect. redondeado",
    "rect": "Rectángulo",
    "heptagon": "Heptágono",
    "hexagon": "Hexágono",
    "pentagon": "Pentágono",
    "octagon": "Octógono",
    "diamond": "Rombo",
}


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
@dataclass
class Cell:
    row: int
    col: int
    value: object = None
    text: str = ""
    bold: bool = False
    italic: bool = False
    size: float = 10.0
    color: str | None = None
    fill: str | None = None
    h_align: str | None = None
    v_align: str | None = None
    wrap: bool = False
    rotation: int = 0
    borders: dict = field(default_factory=dict)  # side -> (style, color)
    is_number: bool = False


@dataclass
class Merge:
    r1: int
    c1: int
    r2: int
    c2: int


@dataclass
class Shape:
    geom: str
    text: str
    fill: str | None           # '#RRGGBB' o None (sin relleno)
    line: str | None
    line_w: float              # pt
    font_size: float           # pt
    bold: bool
    text_color: str
    v_anchor: str
    c1: int
    c1off: int
    r1: int
    r1off: int
    c2: int
    c2off: int
    r2: int
    r2off: int
    # Geometría resuelta en px (hoja completa)
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    idx: int = 0

    @property
    def label(self) -> str:
        return GEOM_ES.get(self.geom, self.geom)

    @property
    def clean_text(self) -> str:
        return self.text.strip()

    @property
    def is_legend_mark(self) -> bool:
        return self.clean_text.lower() == "x"


@dataclass
class Slot:
    block: int
    quadrant: int
    header: str          # ALTO / BAJO
    lado: str            # LADO 10 / LADO 13 / ''
    fila: str            # Superior / Inferior
    lado_pos: str        # Izq / Der
    row: int
    col: int
    page: object
    mark: str            # F / A de ese cuadrante
    shapes: list = field(default_factory=list)  # índices de Shape


@dataclass
class Block:
    """Un pliego/plancha: encabezados ALTO/BAJO + 2 filas de páginas + marcas + LADO."""
    number: int
    header_row: int
    lado_row: int | None
    top_row: int | None
    bottom_row: int | None
    mark_row: int | None
    quadrants: list = field(default_factory=list)  # dicts
    slots: list = field(default_factory=list)


@dataclass
class Band:
    """Sección visual de la hoja (cuerpo / tirada), delimitada por su título."""
    number: int
    r1: int
    r2: int
    title: str
    title_norm: str
    blocks: list = field(default_factory=list)   # índices de Block
    legend: list = field(default_factory=list)   # [(figura, etiqueta)]


@dataclass
class SheetModel:
    name: str
    folio: str
    col_px: dict
    row_px: dict
    col_x: dict
    row_y: dict
    cells: dict
    merges: list
    merge_of: dict
    shapes: list
    max_row: int
    min_col: int
    max_col: int
    blocks: list = field(default_factory=list)
    bands: list = field(default_factory=list)
    header_texts: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    # ---- geometría ----
    def cell_rect(self, r, c):
        m = self.merge_of.get((r, c))
        if m:
            r1, c1, r2, c2 = m.r1, m.c1, m.r2, m.c2
        else:
            r1, c1, r2, c2 = r, c, r, c
        x = self.col_x[c1]
        y = self.row_y[r1]
        w = self.col_x[c2 + 1] - x
        h = self.row_y[r2 + 1] - y
        return x, y, w, h

    def extent(self, r1: int, r2: int) -> int:
        """Última fila real de una región (incluye figuras y celdas combinadas que la exceden)."""
        r_end = r2
        for s in self.shapes:
            if r1 <= s.r1 <= r2:
                r_end = max(r_end, s.r2)
        for m in self.merges:
            if r1 <= m.r1 <= r2:
                cell = self.cells.get((m.r1, m.c1))
                if cell is not None and (cell.text or cell.borders or cell.fill):
                    r_end = max(r_end, m.r2)
        return r_end

    def value(self, r, c):
        cell = self.cells.get((r, c))
        return cell.value if cell else None


@dataclass
class IndexEntry:
    key: str
    total: int
    config: str
    folio: str
    sheet: str | None
    kind: str                  # 'variante' (hojas 1-12b) | 'tiradas' (13 en adelante)
    tapa_pags: object = None
    tapa_conf: str = ""
    suples: str = ""
    tiradas: list = field(default_factory=list)
    n_tiradas: object = None
    band: int | None = None    # banda de la hoja (solo 'variante')
    fecha: object = None
    index_row: int = 0

    @property
    def label(self) -> str:
        if self.kind == "variante":
            return f"{self.config}   ·   plantilla {self.folio}"
        partes = [f"Tapa {self.tapa_conf}"]
        if self.suples:
            partes.append(f"Suples {self.suples}")
        tir = " | ".join(self.tiradas)
        return f"{self.config}   ·   {' + '.join(partes)}   ·   Tiradas: {tir}   ·   plantilla {self.folio}"


@dataclass
class Library:
    path: str
    file_hash: str
    title: str
    entries: list
    sheets: dict
    warnings: list

    def totals(self):
        return sorted({e.total for e in self.entries if e.sheet})

    def options(self, total: int):
        return [e for e in self.entries if e.total == total and e.sheet]


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _fmt_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v)


def _strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def norm_config(s) -> str:
    """'20 + 4 = 24 págs.' -> '20+4' ; '12 págs. ' -> '12' ; 16 -> '16'."""
    n = re.sub(r"\s", "", _fmt_value(s).lower())
    n = n.split("=")[0]
    n = re.sub(r"p[áa]gs?\.?", "", n)
    n = re.sub(r"p\.?$", "", n)
    return n.strip(".,;")


def config_total(config: str) -> int | None:
    parts = re.findall(r"\d+", config)
    if not parts or not re.fullmatch(r"\d+(\+\d+)*", config):
        return None
    return sum(int(p) for p in parts)


def folio_of_sheet(name: str) -> str | None:
    m = re.match(r"\s*(\d+[a-zA-Z]?)\s*\)", name)
    return m.group(1).lower() if m else None


def _px_col(width) -> int:
    return int(round(width * 7)) if width is not None else 64


def _px_row(height_pt) -> int:
    return int(height_pt * 4 / 3)


# --------------------------------------------------------------------------- #
# Figuras (DrawingML)
# --------------------------------------------------------------------------- #
def _sheet_drawing_map(z: zipfile.ZipFile) -> dict:
    """nombre de hoja -> ruta del drawing xml dentro del zip."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for s in wb.find(f"{NS_MAIN}sheets"):
        target = rid_target.get(s.get(f"{NS_REL}id"), "")
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = posixpath.normpath(posixpath.join("xl", target))
        rel_path = posixpath.join(posixpath.dirname(target), "_rels", posixpath.basename(target) + ".rels")
        if rel_path not in z.namelist():
            continue
        for r in ET.fromstring(z.read(rel_path)):
            t = r.get("Target", "")
            if r.get("Type", "").endswith("/drawing"):
                dpath = posixpath.normpath(posixpath.join(posixpath.dirname(target), t))
                out[s.get("name")] = dpath
    return out


def _parse_shapes(xml_bytes: bytes, theme: dict) -> list:
    root = ET.fromstring(xml_bytes)
    shapes = []
    for anc in root:
        if anc.tag != f"{XDR}twoCellAnchor":
            continue
        fr, to = anc.find(f"{XDR}from"), anc.find(f"{XDR}to")
        if fr is None or to is None:
            continue

        def g(e, t):
            return int(e.find(f"{XDR}{t}").text)

        for sp in anc:
            if sp.tag not in (f"{XDR}sp", f"{XDR}cxnSp"):
                continue
            sppr = sp.find(f"{XDR}spPr")
            geo = sppr.find(f"{A}prstGeom") if sppr is not None else None
            geom = geo.get("prst") if geo is not None else "rect"
            # relleno
            fill = None
            if sppr is not None:
                if sppr.find(f"{A}noFill") is not None:
                    fill = None
                else:
                    fill = drawingml_color(sppr.find(f"{A}solidFill"), theme)
            # línea
            line, line_w = "#000000", 0.75
            ln = sppr.find(f"{A}ln") if sppr is not None else None
            if ln is not None:
                if ln.get("w"):
                    line_w = int(ln.get("w")) / 12700
                if ln.find(f"{A}noFill") is not None:
                    line = None
                else:
                    line = drawingml_color(ln.find(f"{A}solidFill"), theme) or "#000000"
            # texto
            texts, size, bold, tcolor = [], None, False, "#000000"
            body = sp.find(f"{XDR}txBody")
            v_anchor = "t"
            if body is not None:
                bp = body.find(f"{A}bodyPr")
                if bp is not None:
                    v_anchor = bp.get("anchor", "t")
                for p in body.findall(f"{A}p"):
                    line_txt = "".join(t.text or "" for t in p.iter(f"{A}t"))
                    texts.append(line_txt)
                    for rpr in list(p.iter(f"{A}rPr")) + list(p.iter(f"{A}defRPr")):
                        if size is None and rpr.get("sz"):
                            size = int(rpr.get("sz")) / 100
                        if rpr.get("b") == "1":
                            bold = True
                        c = drawingml_color(rpr.find(f"{A}solidFill"), theme)
                        if c:
                            tcolor = c
            text = "\n".join(t for t in texts if t is not None).strip("\n")
            shapes.append(Shape(
                geom=geom, text=text, fill=fill, line=line, line_w=line_w,
                font_size=size or 11.0, bold=bold, text_color=tcolor, v_anchor=v_anchor,
                c1=g(fr, "col") + 1, c1off=g(fr, "colOff"), r1=g(fr, "row") + 1, r1off=g(fr, "rowOff"),
                c2=g(to, "col") + 1, c2off=g(to, "colOff"), r2=g(to, "row") + 1, r2off=g(to, "rowOff"),
            ))
    return shapes


# --------------------------------------------------------------------------- #
# Hoja-plantilla
# --------------------------------------------------------------------------- #
def _read_sheet(ws, folio, theme, shapes) -> SheetModel:
    merges, merge_of = [], {}
    for mr in ws.merged_cells.ranges:
        m = Merge(mr.min_row, mr.min_col, mr.max_row, mr.max_col)
        merges.append(m)
        for r in range(m.r1, m.r2 + 1):
            for c in range(m.c1, m.c2 + 1):
                merge_of[(r, c)] = m

    cells = {}
    max_row, min_col, max_col = 1, 10 ** 6, 1
    for row in ws.iter_rows():
        for c in row:
            v = c.value
            b = c.border
            borders = {}
            for side in ("left", "right", "top", "bottom"):
                s = getattr(b, side)
                if s is not None and s.style:
                    borders[side] = (s.style, openpyxl_color(s.color, theme, is_fill=False) or "#000000")
            fill = None
            if c.fill is not None and c.fill.fill_type == "solid":
                fill = openpyxl_color(c.fill.fgColor, theme, is_fill=True)
                if fill and fill.upper() == "#FFFFFF":
                    fill = None
            if v is None and not borders and not fill:
                continue
            if isinstance(v, str) and not v.strip() and not borders and not fill:
                continue
            f = c.font
            al = c.alignment
            cell = Cell(
                row=c.row, col=c.column, value=v, text=_fmt_value(v),
                bold=bool(f.b), italic=bool(f.i), size=float(f.sz or 10),
                color=openpyxl_color(f.color, theme, is_fill=False) if f.color is not None else None,
                fill=fill,
                h_align=al.horizontal, v_align=al.vertical, wrap=bool(al.wrap_text),
                rotation=int(al.textRotation or 0), borders=borders,
                is_number=isinstance(v, (int, float)) and not isinstance(v, bool),
            )
            cells[(c.row, c.column)] = cell
            if v is not None and str(v).strip():
                max_row = max(max_row, c.row)
                min_col = min(min_col, c.column)
                max_col = max(max_col, c.column)

    for s in shapes:
        max_row = max(max_row, s.r2)
        max_col = max(max_col, s.c2)
        min_col = min(min_col, s.c1)
    for m in merges:
        if (m.r1, m.c1) in cells and cells[(m.r1, m.c1)].text:
            max_col = max(max_col, m.c2)
            max_row = max(max_row, m.r2)
    if min_col == 10 ** 6:
        min_col = 1
    # descartar celdas con solo borde fuera del área útil
    cells = {k: v for k, v in cells.items() if k[0] <= max_row + 2 and min_col <= k[1] <= max_col + 1}

    # geometría
    widths = {}
    default_w = ws.sheet_format.defaultColWidth
    if default_w is None and ws.sheet_format.baseColWidth is not None:
        default_w = ws.sheet_format.baseColWidth + 0.71
    for dim in ws.column_dimensions.values():
        if dim.min is None:
            continue
        for ci in range(dim.min, min(dim.max or dim.min, max_col + 3) + 1):
            widths[ci] = 0 if dim.hidden else _px_col(dim.width if dim.width else default_w)
    col_px = {ci: widths.get(ci, _px_col(default_w)) for ci in range(1, max_col + 4)}
    default_h = ws.sheet_format.defaultRowHeight or 12.75
    row_px = {}
    for ri in range(1, max_row + 4):
        d = ws.row_dimensions.get(ri)
        if d is not None and d.hidden:
            row_px[ri] = 0
        else:
            h = d.height if (d is not None and d.height) else default_h
            row_px[ri] = _px_row(h)
    col_x, x = {}, 0
    for ci in range(1, max_col + 4):
        col_x[ci] = x
        x += col_px[ci]
    col_x[max_col + 4] = x
    row_y, y = {}, 0
    for ri in range(1, max_row + 4):
        row_y[ri] = y
        y += row_px[ri]
    row_y[max_row + 4] = y

    end_x, end_y = col_x[max_col + 4], row_y[max_row + 4]

    def at_x(c, off):
        return col_x.get(c, end_x) + min(off / EMU_PX, col_px.get(c, 64))

    def at_y(r, off):
        return row_y.get(r, end_y) + min(off / EMU_PX, row_px.get(r, 17))

    for i, s in enumerate(shapes):
        s.idx = i
        x1, y1 = at_x(s.c1, s.c1off), at_y(s.r1, s.r1off)
        x2, y2 = at_x(s.c2, s.c2off), at_y(s.r2, s.r2off)
        s.x, s.y, s.w, s.h = x1, y1, max(4, x2 - x1), max(4, y2 - y1)

    return SheetModel(
        name=ws.title, folio=folio, col_px=col_px, row_px=row_px, col_x=col_x, row_y=row_y,
        cells=cells, merges=merges, merge_of=merge_of, shapes=shapes,
        max_row=max_row, min_col=min_col, max_col=max_col,
    )


# ---- detección de estructura de taller --------------------------------------
def _is_title_cell(cell: Cell) -> bool:
    if not isinstance(cell.value, str):
        return False
    s = cell.value.strip()
    if not s or s.upper() in KEYWORDS | MARKS or s.upper().startswith("LADO"):
        return False
    if cell.fill and cell.fill.upper() in ("#FFFF99", "#CCFFFF", "#FFCCFF"):
        return True
    if cell.fill and cell.fill.upper() == "#CCFFCC":  # indexado 41 aprox.
        return True
    n = re.sub(r"\s", "", s.lower())
    return bool(re.search(r"p[áa]gs?\.?", n)) or bool(re.fullmatch(r"\d+(\+\d+)+", n))


def _detect_structure(sm: SheetModel):
    cells = sm.cells
    # --- encabezados ALTO/BAJO
    header_rows = {}
    for (r, c), cell in cells.items():
        if isinstance(cell.value, str) and cell.value.strip().upper() in KEYWORDS:
            header_rows.setdefault(r, []).append(c)
    lado_cells = [(r, c, cell.text.strip().upper()) for (r, c), cell in cells.items()
                  if isinstance(cell.value, str) and cell.value.strip().upper().startswith("LADO")]

    blocks = []
    for bi, h in enumerate(sorted(header_rows)):
        cols = sorted(header_rows[h])
        lado_row = min((r for r, _, _ in lado_cells if h < r <= h + 20), default=None)
        end = lado_row if lado_row else h + 12
        quads = []
        for c in cols:
            m = sm.merge_of.get((h, c))
            c1, c2 = (m.c1, m.c2) if m else (c, c + 1)
            page_cols = list(range(c1, c2 + 1)) if c2 > c1 else [c1, c1 + 1]
            quads.append({"header": cells[(h, c)].text.strip().upper(), "cols": page_cols,
                          "mark_col": c1 - 1, "mark": "", "lado": ""})
        # fila de marcas F/A
        mark_row = None
        for r in range(h + 1, end):
            for q in quads:
                v = sm.value(r, q["mark_col"])
                if isinstance(v, str) and v.strip().upper() in MARKS:
                    mark_row = r if mark_row is None else mark_row
                    q["mark"] = q["mark"] or v.strip().upper()
            if mark_row is not None:
                break
        # filas de páginas
        num_rows = sorted({r for r in range(h + 1, end) for q in quads for c in q["cols"]
                           if cells.get((r, c)) is not None and cells[(r, c)].text
                           and (r, c) == ((sm.merge_of[(r, c)].r1, sm.merge_of[(r, c)].c1)
                                          if (r, c) in sm.merge_of else (r, c))})
        if mark_row is not None:
            top = max([r for r in num_rows if r < mark_row], default=mark_row - 2)
            bottom = min([r for r in num_rows if r > mark_row], default=mark_row + 1)
        else:
            top = num_rows[0] if num_rows else h + 3
            bottom = num_rows[1] if len(num_rows) > 1 else top + 3
        extra = [r for r in num_rows if r not in (top, bottom)]
        if extra:
            sm.warnings.append(f"Pliego en fila {h}: números fuera de las filas esperadas {extra}")
        # LADO por cercanía de columna
        lados = [(c, t) for r, c, t in lado_cells if r == lado_row]
        for q in quads:
            if lados:
                qc = (q["cols"][0] + q["cols"][-1]) / 2
                q["lado"] = min(lados, key=lambda lc: abs(lc[0] - qc))[1]
        blk = Block(number=bi + 1, header_row=h, lado_row=lado_row, top_row=top,
                    bottom_row=bottom, mark_row=mark_row, quadrants=quads)
        for qi, q in enumerate(quads):
            for fila, r in (("Superior", top), ("Inferior", bottom)):
                for pos_i, c in enumerate(q["cols"][:2]):
                    blk.slots.append(Slot(
                        block=bi, quadrant=qi, header=q["header"], lado=q["lado"], fila=fila,
                        lado_pos="Izq" if pos_i == 0 else "Der", row=r, col=c,
                        page=sm.value(r, c), mark=q["mark"]))
        blocks.append(blk)
    sm.blocks = blocks

    # --- asignación de figuras a posiciones de página
    for s in sm.shapes:
        if s.is_legend_mark or (s.fill and s.fill.upper() == "#FFCC99"):
            continue
        best, best_area = None, 0.0
        for blk in blocks:
            for slot in blk.slots:
                x, y, w, h = sm.cell_rect(slot.row, slot.col)
                ox = max(0, min(x + w, s.x + s.w) - max(x, s.x))
                oy = max(0, min(y + h, s.y + s.h) - max(y, s.y))
                if ox * oy > best_area:
                    best, best_area = slot, ox * oy
        if best is not None and best_area >= 0.12 * s.w * s.h:
            best.shapes.append(s.idx)

    # --- bandas (secciones con título)
    title_rows = {}
    for (r, c), cell in sorted(cells.items()):
        if _is_title_cell(cell):
            title_rows.setdefault(r, cell.text.strip())
    starts = sorted(title_rows)
    first_block = blocks[0].header_row if blocks else 10 ** 6
    pre = [r for r in starts if r < first_block]
    bands_rows = []
    cur_start, cur_title = 1, (title_rows[pre[-1]] if pre else None)
    for r in (r for r in starts if r > first_block):
        if any(cur_start <= b.header_row < r for b in blocks):
            bands_rows.append((cur_start, r - 1, cur_title))
            cur_start, cur_title = r, title_rows[r]
    bands_rows.append((cur_start, sm.max_row, cur_title))

    # títulos de cabecera (fila 1-3): fórmula general, "N tiradas"
    sm.header_texts = [cells[k].text.strip() for k in sorted(cells) if k[0] <= 3 and cells[k].text.strip()
                       and cells[k].text.strip() not in (",",)]

    bands = []
    for i, (r1, r2, title) in enumerate(bands_rows):
        # cortar filas finales vacías
        def row_has_content(r):
            if any(cells.get((r, c)) is not None for c in range(sm.min_col, sm.max_col + 2)):
                return True
            return any(s.r1 <= r <= s.r2 for s in sm.shapes)
        while r2 > r1 and not row_has_content(r2):
            r2 -= 1
        b = Band(number=i + 1, r1=r1, r2=r2, title=title or "",
                 title_norm=norm_config(title) if title else "",
                 blocks=[bi for bi, blk in enumerate(blocks) if r1 <= blk.header_row <= r2])
        bands.append(b)
    sm.bands = bands
    _detect_legends(sm)


def _detect_legends(sm: SheetModel):
    """Referencias tipo 'X Suple 1 / (óvalo) X Suple 2 ...'."""
    texts = [(k, c) for k, c in sm.cells.items()
             if isinstance(c.value, str) and c.value.strip() and c.value.strip().lower() not in ("x",)]

    def label_right_of(x_ref, y1, y2, exclude_x_max=None):
        cands = []
        for (r, c), cell in texts:
            x, y, w, h = sm.cell_rect(r, c)
            if y + h < y1 - 2 or y > y2 + 2:
                continue
            if x < x_ref - 6:
                continue
            t = cell.text.strip()
            if t.upper() in KEYWORDS | MARKS or t.upper().startswith("LADO") or t.upper() == "REFERENCIAS":
                continue
            dy = abs((y + h / 2) - (y1 + y2) / 2)
            cands.append((max(0, x - x_ref) + 0.6 * dy, r, c, t))
        if not cands:
            return None
        _, r, c, t = min(cands)
        up = sm.cells.get((r - 1, c))
        down = sm.cells.get((r + 1, c))
        if t.startswith("(") and up is not None and up.text.strip():
            t = f"{up.text.strip()} {t}"
        elif down is not None and down.text.strip().startswith("("):
            t = f"{t} {down.text.strip()}"
        return t

    legend_by_band = {b.number: [] for b in sm.bands}

    def band_of_row(r):
        for b in sm.bands:
            if b.r1 <= r <= b.r2:
                return b.number
        return sm.bands[-1].number if sm.bands else None

    for s in sm.shapes:
        if not s.is_legend_mark:
            continue
        lab = label_right_of(s.x + s.w / 2, s.y, s.y + s.h)
        if lab:
            legend_by_band[band_of_row(s.r1)].append((s.label, lab))
    # celdas "X" sin figura encima = páginas sin figura
    for (r, c), cell in sm.cells.items():
        if not (isinstance(cell.value, str) and cell.value.strip().lower() == "x"):
            continue
        x, y, w, h = sm.cell_rect(r, c)
        covered = any(s.is_legend_mark and s.x < x + w and s.x + s.w > x and s.y < y + h and s.y + s.h > y
                      for s in sm.shapes)
        if covered:
            continue
        lab = label_right_of(x + w * 0.6, y, y + h)
        if lab:
            legend_by_band[band_of_row(r)].append(("Sin figura", lab))
    for b in sm.bands:
        seen, out = set(), []
        for item in legend_by_band.get(b.number, []):
            if item not in seen:
                seen.add(item)
                out.append(item)
        b.legend = out


def legend_for(sm: SheetModel, band: Band) -> list:
    """Referencias aplicables a una banda (propias o, si no tiene, las de la hoja)."""
    if band.legend:
        return band.legend
    for b in sm.bands:
        if b.legend:
            return b.legend
    return []


# --------------------------------------------------------------------------- #
# Índice
# --------------------------------------------------------------------------- #
def _split_cfg(v) -> str:
    return re.sub(r"\s", "", _fmt_value(v))


def _read_index(ws, folio_to_sheet: dict) -> tuple[list, str, list]:
    entries, warnings = [], []
    title = ""
    mode = "variante"
    header_seen = 0
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        vals = {c.column: c.value for c in row if c.value is not None}
        r = row[0].row
        if not vals:
            continue
        if r == 1:
            title = " ".join(_fmt_value(v) for v in vals.values()).strip()
            continue
        if any(isinstance(v, str) and "totales" in v.lower() for v in vals.values()):
            header_seen += 1
            if header_seen >= 2:
                mode = "tiradas"
            continue
        folio = vals.get(11)
        if folio is None:
            continue
        folio = _fmt_value(folio).strip().lower()
        sheet = folio_to_sheet.get(folio)
        if sheet is None:
            warnings.append(f"Índice fila {r}: no hay hoja para la plantilla '{folio}'")
        if mode == "variante":
            for col in range(4, 9):  # D..H
                cfg = vals.get(col)
                if cfg is None:
                    continue
                cfg_s = _split_cfg(cfg)
                tot = config_total(cfg_s)
                if tot is None:
                    warnings.append(f"Índice fila {r}: configuración ilegible '{cfg}'")
                    continue
                entries.append(IndexEntry(
                    key=f"{folio}|{cfg_s}", total=tot, config=cfg_s, folio=folio, sheet=sheet,
                    kind="variante", index_row=r))
        else:
            total = vals.get(2)
            try:
                total = int(total)
            except (TypeError, ValueError):
                warnings.append(f"Índice fila {r}: total ilegible '{total}'")
                continue
            tapa_conf = _split_cfg(vals.get(4, ""))
            suples = _split_cfg(vals.get(5, ""))
            config = "+".join(p for p in (tapa_conf, suples) if p)
            tiradas = [_split_cfg(vals[c]) for c in (6, 7, 8, 9) if c in vals]
            entries.append(IndexEntry(
                key=f"{folio}|{config}|{r}", total=total, config=config, folio=folio, sheet=sheet,
                kind="tiradas", tapa_pags=vals.get(3), tapa_conf=tapa_conf, suples=suples,
                tiradas=tiradas, n_tiradas=vals.get(10), fecha=vals.get(12), index_row=r))
    return entries, title, warnings


# --------------------------------------------------------------------------- #
# Carga principal
# --------------------------------------------------------------------------- #
def load_library_cached(path, cache_dir=None) -> Library:
    """Igual que load_library pero guarda/lee un pickle por hash del archivo."""
    import pickle
    path = str(path)
    h = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    cache_dir = Path(cache_dir or Path(__file__).resolve().parent.parent / ".cache")
    f = cache_dir / f"lib_{PARSER_VERSION}_{h}.pkl"
    if f.exists():
        try:
            lib = pickle.loads(f.read_bytes())
            lib.path = path
            return lib
        except Exception:
            pass
    lib = load_library(path)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        f.write_bytes(pickle.dumps(lib))
    except Exception:
        pass
    return lib


def load_library(path) -> Library:
    path = str(path)
    data = Path(path).read_bytes()
    file_hash = hashlib.sha1(data).hexdigest()
    theme = load_theme(path)
    wb = openpyxl.load_workbook(path, data_only=True)
    with zipfile.ZipFile(path) as z:
        dmap = _sheet_drawing_map(z)
        drawings = {name: _parse_shapes(z.read(p), theme) for name, p in dmap.items() if p in z.namelist()}

    index_ws = next((ws for ws in wb.worksheets if _strip_accents(ws.title.lower()).startswith(INDEX_SHEET_HINT)),
                    wb.worksheets[0])
    folio_to_sheet = {}
    for ws in wb.worksheets:
        f = folio_of_sheet(ws.title)
        if f:
            folio_to_sheet[f] = ws.title

    entries, title, warnings = _read_index(index_ws, folio_to_sheet)
    sheets = {}
    for name in sorted(set(folio_to_sheet.values()), key=lambda n: wb.sheetnames.index(n)):
        ws = wb[name]
        sm = _read_sheet(ws, folio_of_sheet(name), theme, drawings.get(name, []))
        _detect_structure(sm)
        sheets[name] = sm
        warnings.extend(f"[{name}] {w}" for w in sm.warnings)

    # vincular variantes con su banda
    for e in entries:
        if e.kind != "variante" or not e.sheet:
            continue
        sm = sheets[e.sheet]
        match = [b for b in sm.bands if b.title_norm == e.config]
        if not match and len(sm.bands) == 1:
            match = sm.bands
        if match:
            e.band = match[0].number
        else:
            warnings.append(f"Índice: la combinación '{e.config}' (plantilla {e.folio}) no se encontró como "
                            f"sección en la hoja '{e.sheet}'; se mostrará la hoja completa.")
    return Library(path=path, file_hash=file_hash, title=title, entries=entries, sheets=sheets, warnings=warnings)


def col_letter(c: int) -> str:
    return get_column_letter(c)
