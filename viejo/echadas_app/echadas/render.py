"""
Lista de dibujo (display list) y motores de salida del plano.

Una sola geometría alimenta a los dos motores de salida (SVG en pantalla y
ReportLab en PDF), así lo que se ve es exactamente lo que se imprime.
Unidades: píxeles a 96 dpi, origen arriba-izquierda de la región.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape


FONT_STACK = "Arial, Helvetica, sans-serif"

BORDER_W = {"hair": 0.5, "thin": 1.0, "medium": 2.0, "thick": 3.0, "double": 2.5,
            "dashed": 1.0, "dotted": 1.0, "mediumDashed": 2.0, "dashDot": 1.0,
            "mediumDashDot": 2.0, "dashDotDot": 1.0, "mediumDashDotDot": 2.0, "slantDashDot": 2.0}
BORDER_DASH = {"dashed": (4, 2), "dotted": (1, 2), "mediumDashed": (6, 3), "dashDot": (6, 2, 1, 2),
               "mediumDashDot": (6, 2, 1, 2), "dashDotDot": (6, 2, 1, 2, 1, 2),
               "mediumDashDotDot": (6, 2, 1, 2, 1, 2), "slantDashDot": (6, 2, 1, 2)}

# rectángulo de texto de cada figura (fracciones de w/h), según presets de Office
TEXT_RECT = {
    "ellipse": (0.146, 0.146, 0.854, 0.854),
    "triangle": (0.25, 0.5, 0.75, 1.0),
    "roundRect": (0.05, 0.05, 0.95, 0.95),
    "heptagon": (0.15, 0.2, 0.85, 0.85),
    "hexagon": (0.2, 0.1, 0.8, 0.9),
    "pentagon": (0.2, 0.3, 0.8, 0.9),
    "octagon": (0.15, 0.15, 0.85, 0.85),
    "diamond": (0.25, 0.25, 0.75, 0.75),
}


@dataclass
class Drawing:
    width: float
    height: float
    ops: list = field(default_factory=list)


def shape_points(geom, x, y, w, h):
    """Polígono para figuras sin primitiva propia (None = usar primitiva)."""
    if geom == "triangle":
        return [(x + w / 2, y), (x + w, y + h), (x, y + h)]
    if geom == "hexagon":
        return [(x, y + h / 2), (x + w * 0.25, y), (x + w * 0.75, y), (x + w, y + h / 2),
                (x + w * 0.75, y + h), (x + w * 0.25, y + h)]
    if geom == "diamond":
        return [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
    if geom == "octagon":
        k = 0.29
        return [(x + w * k, y), (x + w * (1 - k), y), (x + w, y + h * k), (x + w, y + h * (1 - k)),
                (x + w * (1 - k), y + h), (x + w * k, y + h), (x, y + h * (1 - k)), (x, y + h * k)]
    if geom in ("heptagon", "pentagon"):
        n = 7 if geom == "heptagon" else 5
        pts = [(math.cos(-math.pi / 2 + 2 * math.pi * i / n), math.sin(-math.pi / 2 + 2 * math.pi * i / n))
               for i in range(n)]
        minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
        miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
        return [(x + (px - minx) / (maxx - minx) * w, y + (py - miny) / (maxy - miny) * h) for px, py in pts]
    return None


def _wrap(text, width_px, size_px):
    avg = size_px * 0.55
    max_chars = max(1, int(width_px / avg))
    out = []
    for para in text.split("\n"):
        words, line = para.split(" "), ""
        for wd in words:
            cand = (line + " " + wd).strip()
            if len(cand) <= max_chars or not line:
                line = cand
            else:
                out.append(line)
                line = wd
        out.append(line)
    return out


# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #
def _shape_text_pos(geom, x, y, w, h, size_px):
    l, t, r, b = TEXT_RECT.get(geom, (0, 0, 1, 1))
    tx = x + w * (l + r) / 2
    ty = y + h * (t + b) / 2 + size_px * 0.36
    return tx, ty


def to_svg(d: Drawing, max_width: int | None = None, title: str = "") -> str:
    W, H = math.ceil(d.width) + 2, math.ceil(d.height) + 2
    style = f"max-width:{max_width or W}px;width:100%;height:auto;background:#fff"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {W} {H}" '
           f'style="{style}" font-family="{FONT_STACK}" role="img">']
    if title:
        out.append(f"<title>{escape(title)}</title>")
    for op in d.ops:
        kind = op[0]
        if kind == "rect":
            _, x, y, w, h, fill = op
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>')
        elif kind == "line":
            _, x1, y1, x2, y2, bw, color, dash = op
            da = f' stroke-dasharray="{",".join(str(v) for v in dash)}"' if dash else ""
            out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                       f'stroke-width="{bw}" stroke-linecap="square"{da}/>')
        elif kind == "text":
            _, x, y, txt, size, bold, italic, color, anchor = op
            out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" '
                       f'font-weight="{"bold" if bold else "normal"}" '
                       f'font-style="{"italic" if italic else "normal"}" fill="{color}" '
                       f'text-anchor="{anchor}" xml:space="preserve">{escape(txt)}</text>')
        elif kind == "shape":
            _, geom, x, y, w, h, fill, line, lw, txt, size, bold, tcolor = op
            f = fill or "none"
            st = line or "none"
            common = f'fill="{f}" stroke="{st}" stroke-width="{lw:.2f}"'
            pts = shape_points(geom, x, y, w, h)
            if geom == "ellipse":
                out.append(f'<ellipse cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" rx="{w / 2:.1f}" '
                           f'ry="{h / 2:.1f}" {common}/>')
            elif geom == "roundRect":
                rr = min(w, h) * 0.1667
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rr:.1f}" {common}/>')
            elif pts:
                p = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
                out.append(f'<polygon points="{p}" {common}/>')
            else:
                out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" {common}/>')
            if txt:
                tx, ty = _shape_text_pos(geom, x, y, w, h, size)
                out.append(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="{size:.1f}" '
                           f'font-weight="{"bold" if bold else "normal"}" fill="{tcolor}" '
                           f'text-anchor="middle">{escape(txt)}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# ReportLab
# --------------------------------------------------------------------------- #
def rl_font(bold, italic):
    if bold and italic:
        return "Helvetica-BoldOblique"
    if bold:
        return "Helvetica-Bold"
    if italic:
        return "Helvetica-Oblique"
    return "Helvetica"


def draw_reportlab(canv, d: Drawing, ox: float, oy_top: float, scale: float):
    """Dibuja la región en un canvas ReportLab. (ox, oy_top) = esquina sup. izq. en pt."""
    from reportlab.lib.colors import HexColor

    def X(v):
        return ox + v * scale

    def Y(v):
        return oy_top - v * scale

    canv.saveState()
    for op in d.ops:
        kind = op[0]
        if kind == "rect":
            _, x, y, w, h, fill = op
            canv.setFillColor(HexColor(fill))
            canv.rect(X(x), Y(y + h), w * scale, h * scale, stroke=0, fill=1)
        elif kind == "line":
            _, x1, y1, x2, y2, bw, color, dash = op
            canv.setStrokeColor(HexColor(color))
            canv.setLineWidth(bw * scale)
            canv.setDash([v * scale for v in dash] if dash else [])
            canv.setLineCap(2)
            canv.line(X(x1), Y(y1), X(x2), Y(y2))
        elif kind == "text":
            _, x, y, txt, size, bold, italic, color, anchor = op
            canv.setFillColor(HexColor(color))
            canv.setFont(rl_font(bold, italic), size * scale)
            if anchor == "middle":
                canv.drawCentredString(X(x), Y(y), txt)
            elif anchor == "end":
                canv.drawRightString(X(x), Y(y), txt)
            else:
                canv.drawString(X(x), Y(y), txt)
        elif kind == "shape":
            _, geom, x, y, w, h, fill, line, lw, txt, size, bold, tcolor = op
            do_fill = 1 if fill else 0
            do_stroke = 1 if line else 0
            if fill:
                canv.setFillColor(HexColor(fill))
            if line:
                canv.setStrokeColor(HexColor(line))
                canv.setLineWidth(max(0.3, lw * scale))
            canv.setDash([])
            pts = shape_points(geom, x, y, w, h)
            if geom == "ellipse":
                canv.ellipse(X(x), Y(y + h), X(x + w), Y(y), stroke=do_stroke, fill=do_fill)
            elif geom == "roundRect":
                canv.roundRect(X(x), Y(y + h), w * scale, h * scale, min(w, h) * 0.1667 * scale,
                               stroke=do_stroke, fill=do_fill)
            elif pts:
                p = canv.beginPath()
                p.moveTo(X(pts[0][0]), Y(pts[0][1]))
                for px, py in pts[1:]:
                    p.lineTo(X(px), Y(py))
                p.close()
                canv.drawPath(p, stroke=do_stroke, fill=do_fill)
            else:
                canv.rect(X(x), Y(y + h), w * scale, h * scale, stroke=do_stroke, fill=do_fill)
            if txt:
                tx, ty = _shape_text_pos(geom, x, y, w, h, size)
                canv.setFillColor(HexColor(tcolor))
                canv.setFont(rl_font(bold, False), size * scale)
                canv.drawCentredString(X(tx), Y(ty), txt)
    canv.restoreState()
