"""Selección de secciones y datos estructurados comunes a pantalla, PDF y Excel."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .loader import Band, IndexEntry, Library, SheetModel, legend_for

ABBR = {"Óvalo": "O", "Triángulo": "T", "Rect. redondeado": "R", "Heptágono": "H",
        "Hexágono": "X", "Rectángulo": "C", "Pentágono": "P", "Octógono": "G", "Rombo": "D"}


@dataclass
class Job:
    """Datos del trabajo que completa el usuario (encabezado de exportaciones)."""
    publicacion: str = ""
    edicion: str = ""
    orden: str = ""
    responsable: str = ""
    destino: str = ""
    observaciones: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Selection:
    lib: Library
    entry: IndexEntry
    sheet: SheetModel
    bands: list
    full_sheet: bool
    generated: datetime = field(default_factory=datetime.now)

    @property
    def blocks(self):
        return [self.sheet.blocks[i] for b in self.bands for i in b.blocks]

    @property
    def legend(self):
        seen, out = set(), []
        for b in self.bands:
            for item in legend_for(self.sheet, b):
                if item not in seen:
                    seen.add(item)
                    out.append(item)
        return out


def select(lib: Library, entry: IndexEntry, full_sheet: bool = False) -> Selection:
    sm = lib.sheets[entry.sheet]
    if entry.kind == "variante" and entry.band and not full_sheet:
        bands = [b for b in sm.bands if b.number == entry.band]
    else:
        bands = list(sm.bands)
    return Selection(lib=lib, entry=entry, sheet=sm, bands=bands, full_sheet=full_sheet or entry.band is None)


def summary_rows(sel: Selection) -> list[tuple[str, str]]:
    e = sel.entry
    rows = [
        ("Total de páginas", str(e.total)),
        ("Combinación", e.config),
        ("Plantilla (folio)", e.folio),
        ("Hoja de origen", sel.sheet.name.strip()),
    ]
    if e.kind == "tiradas":
        rows += [
            ("Págs. tapa", _s(e.tapa_pags)),
            ("Configuración tapa", e.tapa_conf),
            ("Págs. suples", e.suples or "—"),
            ("Tiradas", "  |  ".join(e.tiradas)),
            ("N° de tiradas", _s(e.n_tiradas)),
        ]
    rows.append(("Pliegos en el plano", str(len(sel.blocks))))
    if e.kind == "tiradas" and sel.sheet.header_texts:
        rows.append(("Fórmula de la plantilla", "  ·  ".join(sel.sheet.header_texts[:2])))
    return rows


def _s(v):
    if v is None:
        return "—"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _page(v):
    return _s(v) if v not in (None, "") else ""


def positions_rows(sel: Selection) -> list[dict]:
    sm = sel.sheet
    rows = []
    for band in sel.bands:
        leg = dict()
        for fig, lab in legend_for(sm, band):
            leg.setdefault(fig, lab)
        for bi in band.blocks:
            blk = sm.blocks[bi]
            for sl in blk.slots:
                figs = [sm.shapes[i] for i in sl.shapes]
                base = {
                    "Sección": band.number,
                    "Título sección": band.title,
                    "Pliego": blk.number,
                    "Lado": sl.lado,
                    "Cuadrante": sl.header,
                    "Marca": sl.mark,
                    "Fila": sl.fila,
                    "Posición": sl.lado_pos,
                    "Página (plancha)": _page(sl.page),
                }
                if figs:
                    for f in figs:
                        rows.append({**base, "Figura": f.label, "Nº en figura": f.clean_text,
                                     "Referencia": leg.get(f.label, "")})
                else:
                    rows.append({**base, "Figura": "", "Nº en figura": "",
                                 "Referencia": leg.get("Sin figura", "") if _page(sl.page) else ""})
    return rows


def block_grid(sm: SheetModel, blk) -> tuple[list[str], list[list[str]]]:
    """Tabla compacta de un pliego: columnas = cuadrante/posición, filas = Superior/Inferior."""
    headers, cols = [], []
    for qi, q in enumerate(blk.quadrants):
        for pos in ("Izq", "Der"):
            headers.append(f"{q['lado'].replace('LADO ', 'L')} {q['header']} {q['mark']} · {pos}".strip())
            cols.append((qi, pos))
    grid = []
    for fila in ("Superior", "Inferior"):
        row = []
        for qi, pos in cols:
            sl = next((s for s in blk.slots if s.quadrant == qi and s.lado_pos == pos and s.fila == fila), None)
            if sl is None:
                row.append("")
                continue
            txt = _page(sl.page)
            for i in sl.shapes:
                s = sm.shapes[i]
                if s.clean_text:
                    txt += f" [{ABBR.get(s.label, '?')}{s.clean_text}]"
                else:
                    txt += f" [{ABBR.get(s.label, '?')}]"
            row.append(txt.strip())
        grid.append(row)
    return headers, grid
