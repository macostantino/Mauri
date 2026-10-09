"""Exportación PDF (ReportLab) de una echada GENERADA: orden de imposición para taller."""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A3, A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from .dibujo import tirada_drawing, tirada_titulo
from .generador import Echada
from .render import draw_reportlab
from .tablas import ABBR, composicion, grilla, resumen

INK = colors.HexColor("#1B1B1B")
MUTED = colors.HexColor("#5F6368")
ACCENT = colors.HexColor("#B3261E")
RULE = colors.HexColor("#C9CCD1")
BAND_BG = colors.HexColor("#F1F3F4")
OK_BG = colors.HexColor("#E6F4EA")
BAD_BG = colors.HexColor("#FCE8E6")


@dataclass
class Job:
    publicacion: str = ""
    edicion: str = ""
    orden: str = ""
    responsable: str = ""
    destino: str = ""
    observaciones: str = ""


class PlanFlowable(Flowable):
    def __init__(self, drawing, max_w, max_h, max_scale=0.85):
        super().__init__()
        self.d = drawing
        self.scale = min(max_w / drawing.width, max_scale, max_h / drawing.height)
        self.width = drawing.width * self.scale
        self.height = drawing.height * self.scale
        self.hAlign = "CENTER"

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        draw_reportlab(self.canv, self.d, 0, self.height, self.scale)


LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
PIE_TEXTO = "Generador de echadas Full Color · by "
PIE_MARCA = "nosotros"


def _logo_reader():
    try:
        return ImageReader(str(LOGO_PATH)) if LOGO_PATH.exists() else None
    except Exception:  # un logo ilegible no debe impedir generar el PDF
        return None


def _canvas_factory(footer_left: str, footer_2: str):
    logo = _logo_reader()

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                w, _ = self._pagesize
                right = w - 12 * mm
                self.saveState()
                self.setStrokeColor(RULE)
                self.setLineWidth(0.5)
                self.line(12 * mm, 11 * mm, right, 11 * mm)

                # Marca (derecha): logo de la empresa + "Generador de echadas Full Color · by nosotros"
                x_txt = right
                if logo is not None:
                    lh = 8 * mm
                    iw, ih = logo.getSize()
                    lw = lh * iw / ih
                    self.drawImage(logo, right - lw, 2.2 * mm, width=lw, height=lh, mask="auto")
                    x_txt = right - lw - 2 * mm
                self.setFont("Helvetica-Bold", 7)
                self.setFillColor(INK)
                self.drawRightString(x_txt, 7.5 * mm, PIE_MARCA)
                self.setFont("Helvetica", 7)
                self.setFillColor(MUTED)
                self.drawRightString(x_txt - stringWidth(PIE_MARCA, "Helvetica-Bold", 7), 7.5 * mm, PIE_TEXTO)
                self.setFont("Helvetica-Bold", 8)
                self.setFillColor(INK)
                self.drawRightString(x_txt, 4.2 * mm, f"Página {self._pageNumber} de {n}")
                brand_w = stringWidth(PIE_TEXTO, "Helvetica", 7) + stringWidth(PIE_MARCA, "Helvetica-Bold", 7)

                # Texto izquierdo: se recorta si llegara a pisar la marca
                self.setFont("Helvetica", 7)
                self.setFillColor(MUTED)
                max_w = (x_txt - brand_w) - 12 * mm - 4 * mm
                for txt, y in ((footer_left[:150], 7.5 * mm), (footer_2[:150], 4.5 * mm)):
                    while len(txt) > 1 and stringWidth(txt, "Helvetica", 7) > max_w:
                        txt = txt[:-2].rstrip() + "…"
                    self.drawString(12 * mm, y, txt)
                self.restoreState()
                super().showPage()
            super().save()

    return NumberedCanvas


def _esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(ech: Echada, job: Job, *, page="A4", orientation="Vertical", include_grid=True,
              include_signatures=True, repite_8=True, control: str | None = None) -> bytes:
    size = A3 if page == "A3" else A4
    size = landscape(size) if orientation == "Horizontal" else portrait(size)
    buf = io.BytesIO()
    margin = 12 * mm
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=16 * mm, title=f"Echada {ech.config} ({ech.total} págs.)",
                            author="Echadas Full Color", subject="Plano de imposición")
    aw = size[0] - 2 * margin
    ah = size[1] - margin - 16 * mm
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=14, leading=17,
                        textColor=INK, alignment=TA_LEFT)
    lab = ParagraphStyle("lab", parent=ss["Normal"], fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=9)
    val = ParagraphStyle("val", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12)
    sec = ParagraphStyle("sec", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=14)
    small = ParagraphStyle("small", parent=ss["Normal"], fontName="Helvetica", fontSize=7.5, leading=9)
    cellp = ParagraphStyle("cellp", parent=small, fontName="Helvetica-Bold", fontSize=8.5, alignment=1)

    story = []
    title = Table([[Paragraph("PLANO DE IMPOSICIÓN · ECHADA FULL COLOR", h1),
                    Paragraph(f"<b>{ech.total}</b> págs.<br/><font size=9 color='#5F6368'>{_esc(ech.config)}</font>",
                              ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=20, leading=22,
                                             alignment=2, textColor=ACCENT))]],
                  colWidths=[aw * 0.66, aw * 0.34])
    title.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, INK),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [title, Spacer(1, 3 * mm)]

    def kv(pairs, width):
        t = Table([[Paragraph(k, lab), Paragraph(_esc(v), val)] for k, v in pairs],
                  colWidths=[width * 0.42, width * 0.58])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3)]))
        return t

    jobs = [("Publicación / Producto", job.publicacion), ("Edición / Fecha", job.edicion),
            ("Orden de trabajo", job.orden), ("Responsable", job.responsable), ("Destino / Sección", job.destino)]
    colw = (aw - 6 * mm) / 2
    two = Table([[kv([(k, v or "—") for k, v in jobs], colw), kv(resumen(ech), colw)]],
                colWidths=[colw + 3 * mm] * 2)
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))
    story += [two, Spacer(1, 3 * mm)]

    if control:
        ok = control.startswith("IDÉNTICA")
        story += [Paragraph(f"<b>Control contra plantilla de referencia:</b> {_esc(control)}",
                            ParagraphStyle("ctl", parent=small, fontSize=8.5, leading=11,
                                           backColor=OK_BG if ok else BAD_BG, borderPadding=4)),
                  Spacer(1, 3 * mm)]
    if job.observaciones:
        story += [Paragraph("<b>Observaciones:</b> " + _esc(job.observaciones).replace("\n", "<br/>"),
                            ParagraphStyle("obs", parent=small, fontSize=9, leading=11, backColor=BAND_BG,
                                           borderPadding=4)), Spacer(1, 3 * mm)]

    # composición
    comp = composicion(ech)
    data = [[Paragraph(f"<b>{h}</b>", small) for h in ("#", "Cuerpo", "Figura", "Págs.", "Reparto en tiradas")]]
    for r in comp:
        data.append([Paragraph(str(r["#"]), small), Paragraph(_esc(r["Cuerpo"]), small),
                     Paragraph(_esc(r["Figura"]), small), Paragraph(str(r["Págs."]), small),
                     Paragraph(_esc(r["Reparto en tiradas"]), small)])
    t = Table(data, colWidths=[8 * mm, 34 * mm, 30 * mm, 14 * mm, aw - 86 * mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, RULE), ("BACKGROUND", (0, 0), (-1, 0), BAND_BG),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [Paragraph("Composición", sec), t, Spacer(1, 2 * mm)]
    story.append(Paragraph(
        "<b>ALTO / BAJO</b> = orientación del cuadrante · <b>F / A</b> = pliego (1ª / 2ª bobina) · "
        "<b>LADO 10 / LADO 13</b> = caras del pliego. Número sin figura = cuerpo sin figura; "
        "número dentro de figura = página del cuerpo identificado por esa figura.", small))
    for a in ech.avisos:
        story.append(Paragraph(f"<font color='#B3261E'><b>Aviso:</b></font> {_esc(a)}", small))
    story.append(Spacer(1, 3 * mm))

    # tiradas (como en la planilla: de la última a la primera / tapa)
    for tir in reversed(ech.tiradas):
        titulo, detalle = tirada_titulo(ech, tir)
        extra = "   ·   REPITE" if (repite_8 and tir.puede_repetir) else ""
        head = Table([[Paragraph(_esc(titulo) + extra, sec)], [Paragraph(_esc(detalle), small)]],
                     colWidths=[aw])
        head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND_BG),
                                  ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        plan = PlanFlowable(tirada_drawing(ech, tir, repite_8), aw - 6, ah - 40 * mm)
        story.append(CondPageBreak(min(plan.height + 20 * mm, ah)))
        story += [KeepTogether([head, Spacer(1, 2 * mm), plan]), Spacer(1, 3 * mm)]
        if include_grid:
            for web in tir.webs:
                headers, rows = grilla(ech, tir.numero, web)
                n = len(headers)
                data = [[Paragraph(f"<b>Pliego {web}</b>", small)] +
                        [Paragraph(h, ParagraphStyle("hh", parent=small, fontSize=6.5, leading=7.5, alignment=1))
                         for h in headers]]
                for fila, row in zip(("Superior", "Inferior"), rows):
                    data.append([Paragraph(fila, small)] + [Paragraph(_esc(v), cellp) for v in row])
                first = 16 * mm
                g = Table(data, colWidths=[first] + [(aw - first) / n] * n)
                g.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, RULE), ("BACKGROUND", (0, 0), (-1, 0), BAND_BG),
                                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
                story.append(KeepTogether([g, Spacer(1, 1.5 * mm)]))
            story.append(Spacer(1, 3 * mm))
    if include_grid:
        usadas = {c.figura for c in ech.cuerpos if c.figura in ABBR}
        if usadas:
            story.append(Paragraph("Tablas: " + "  ·  ".join(f"[{ABBR[f]}] {f}" for f in ABBR if f in usadas), small))

    if include_signatures:
        story.append(Spacer(1, 6 * mm))
        sig = Table([["Preparó", "Controló (Preimpresión)", "Recibió (Taller / Impresión)"],
                     ["\n\n\nFirma y fecha"] * 3], colWidths=[aw / 3] * 3, rowHeights=[6 * mm, 18 * mm])
        sig.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, INK), ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
                                 ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, 1), "Helvetica", 7),
                                 ("TEXTCOLOR", (0, 1), (-1, 1), MUTED), ("VALIGN", (0, 1), (-1, 1), "BOTTOM"),
                                 ("BACKGROUND", (0, 0), (-1, 0), BAND_BG)]))
        story.append(KeepTogether([sig]))

    doc.build(story, canvasmaker=_canvas_factory(
        f"Echada generada por el motor de imposición · {ech.config} = {ech.total} págs."
        + (f" · OT {job.orden}" if job.orden else ""),
        f"Generado {datetime.now():%d/%m/%Y %H:%M}"))
    return buf.getvalue()
