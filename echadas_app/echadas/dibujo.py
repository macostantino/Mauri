"""
Dibujo del plano de imposición GENERADO (estilo planilla de taller).

Produce la misma lista de dibujo que render.py, así se reutilizan los motores
SVG (pantalla) y ReportLab (PDF).
"""
from __future__ import annotations

from .generador import GEOM, Echada, Tirada, display_pos, pos_info
from .render import Drawing

RED = "#E00000"
INK = "#111111"
MUTED = "#6B7280"
FILL = {"Óvalo": "#FFFFFF", "Triángulo": "#E4DFEC", "Rect. redondeado": "#FDE9D9", "Heptágono": "#C4D79B",
        "Hexágono": "#DAEEF3", "Rombo": "#FFF2CC", "Pentágono": "#F2DCDB", "Octógono": "#D9D9D9"}

CELL_W, CELL_H = 50, 40
MARK_W = 26
QUAD_GAP = 16
BOX_PAD = 12
FACE_GAP = 22
HEAD_H = 26
LADO_H = 28


def _quad_w():
    return MARK_W + 2 * CELL_W


def _box_w(n_quads):
    return BOX_PAD * 2 + n_quads * _quad_w() + (n_quads - 1) * QUAD_GAP


def block_size(medio: bool):
    nq = 1 if medio else 2
    w = 2 * _box_w(nq) + FACE_GAP
    h = HEAD_H + 2 * CELL_H + LADO_H + 12
    return w, h


def _text(ops, x, y, txt, size, bold=True, color=INK, anchor="middle"):
    ops.append(("text", x, y, str(txt), size, bold, False, color, anchor))


def _line(ops, x1, y1, x2, y2, w=2.0, color=INK):
    ops.append(("line", x1, y1, x2, y2, w, color, None))


def draw_block(ops, ech: Echada, t: Tirada, web: str, ox: float, oy: float, repite: bool = False):
    """Un pliego (web F o A) de una tirada. Devuelve (ancho, alto)."""
    medio = t.medio_formato
    w, h = block_size(medio)
    nq = 1 if medio else 2
    bw = _box_w(nq)
    # posiciones dibujadas por cara (0..7) -> columna
    for fi, cara in enumerate(("L10", "L13")):
        bx = ox + fi * (bw + FACE_GAP)
        # caja de la cara
        for seg in ((bx, oy, bx + bw, oy), (bx, oy + h, bx + bw, oy + h), (bx, oy, bx, oy + h),
                    (bx + bw, oy, bx + bw, oy + h)):
            _line(ops, *seg, w=1.0, color="#9CA3AF")
        # cuadrantes presentes en esta cara (en orden de dibujo)
        if cara == "L10":
            quads = [(0, 1), (2, 3)] if not medio else [(2, 3)]          # columnas por cuadrante
        else:
            quads = [(3, 2), (1, 0)] if not medio else [(3, 2)]
        for qi, cols in enumerate(quads):
            qx = bx + BOX_PAD + qi * (_quad_w() + QUAD_GAP)
            cx0 = qx + MARK_W
            header, _ = pos_info(cara, cols[0])
            _text(ops, cx0 + CELL_W, oy + 19, header, 15, color=RED)
            top_y = oy + HEAD_H + 4
            mid_y = top_y + CELL_H
            # cruz
            _line(ops, cx0 - 4, mid_y, cx0 + 2 * CELL_W + 4, mid_y, 2.2)
            _line(ops, cx0 + CELL_W, top_y + 2, cx0 + CELL_W, mid_y + CELL_H - 2, 2.2)
            _text(ops, qx + MARK_W / 2 - 2, mid_y + 7, web, 18, color=RED)
            for k, col in enumerate(cols):
                for fila, y0 in (("top", top_y), ("bot", mid_y)):
                    p = ech.en(t.numero, web, cara, col, fila)
                    rep = False
                    if p is None and repite and t.formato == 8 and col in (0, 1):
                        p = ech.en(t.numero, web, cara, col + 2, fila)
                        rep = p is not None
                    if p is None:
                        continue
                    x = cx0 + k * CELL_W
                    _draw_page(ops, ech, p, x, y0, faded=rep)
        _text(ops, bx + bw / 2, oy + h - 10, "LADO " + cara[1:], 15, color=RED)
    return w, h


def _draw_page(ops, ech, p, x, y, faded=False):
    c = ech.cuerpos[p.cuerpo]
    cx, cy = x + CELL_W / 2, y + CELL_H / 2
    color = "#9CA3AF" if faded else INK
    if c.figura in GEOM:
        sw, sh = 38, 32
        ops.append(("shape", GEOM[c.figura], cx - sw / 2, cy - sh / 2, sw, sh,
                    FILL.get(c.figura, "#FFFFFF"), color, 1.2, str(p.pagina), 16, True, color))
    else:
        _text(ops, cx, cy + 8, p.pagina, 22, color=color)


def tirada_drawing(ech: Echada, t: Tirada, repite_8: bool = True) -> Drawing:
    webs = t.webs
    bw, bh = block_size(t.medio_formato)
    gap = 18
    d = Drawing(width=bw + 4, height=len(webs) * bh + (len(webs) - 1) * gap + 4)
    for i, web in enumerate(webs):
        draw_block(d.ops, ech, t, web, 2, 2 + i * (bh + gap), repite=repite_8)
    return d


def tirada_titulo(ech: Echada, t: Tirada) -> str:
    base = f"Tirada {t.numero} · {t.paginas} págs."
    desc = t.descripcion(ech.cuerpos)
    partes = []
    for ci, n in t.contenido:
        c = ech.cuerpos[ci]
        tag = c.nombre + ("" if c.figura == "Sin figura" else f" ({c.figura})")
        partes.append(f"{tag}: {n}" + ("" if n == c.paginas else f" de {c.paginas}"))
    return f"{base}  —  {desc}", " · ".join(partes)
