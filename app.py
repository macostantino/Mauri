"""
Generador de echadas Full Color — imposición offset (rotativa, formato tabloide)
Ejecutar:  streamlit run app.py

La app CALCULA cada echada con su propio motor (echadas/generador.py): tiradas, pliegos F/A,
LADO 10/13, cuadrantes ALTO/BAJO y la página de cada posición. No lee ningún Excel: la app funciona sola.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from echadas.dibujo import tirada_drawing, tirada_titulo
from echadas.excel import build_xlsx
from echadas.generador import BOBINAS, FIGURAS, Cuerpo, figuras_por_defecto, generar, parse_config, plan_tiradas
from echadas.pdf import Job, build_pdf
from echadas.render import to_svg
from echadas.tablas import composicion, grilla, posiciones

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / ".cache"

st.set_page_config(page_title="Generador de echadas", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
  .block-container {padding-top: 1.5rem; max-width: 1450px;}
  .band-head {background: rgba(128,128,128,.10); border-left: 4px solid #B3261E; padding: .45rem .8rem;
              margin: 1.1rem 0 .5rem; border-radius: 4px;}
  .band-head b {font-size: 1.02rem;} .band-head div {opacity:.75; font-size:.85rem;}
  .plan {background:#fff; border:1px solid rgba(128,128,128,.35); border-radius:6px; padding:10px; overflow-x:auto;}
</style>
""", unsafe_allow_html=True)


def safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")


def nombres_por_defecto(n: int) -> list[str]:
    if n == 1:
        return ["Único"]
    return ["Tapa"] + [f"Suple {i}" for i in range(1, n)]


# --------------------------------------------------------------------------- #
# Barra lateral
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("Datos del trabajo")
    job = Job(
        publicacion=st.text_input("Publicación / Producto"),
        edicion=st.text_input("Edición / Fecha", value=datetime.now().strftime("%d/%m/%Y")),
        orden=st.text_input("Orden de trabajo (OT)"),
        responsable=st.text_input("Responsable"),
        destino=st.text_input("Destino / Sección", placeholder="Impresión, Corte, Expedición…"),
        observaciones=st.text_area("Observaciones para taller", height=80),
    )
    st.header("Exportación")
    c1, c2 = st.columns(2)
    pdf_page = c1.selectbox("Papel", ["A4", "A3"])
    pdf_orient = c2.selectbox("Orientación", ["Vertical", "Horizontal"])
    opt_grid = st.checkbox("PDF: tablas de posiciones por pliego", value=True)
    opt_sigs = st.checkbox("PDF: casilleros de firma", value=True)
    opt_img = st.checkbox("Excel: incluir imagen del plano", value=True)
    opt_rep = st.checkbox("Tiradas de 8 págs.: marcar REPITE", value=True)
    out_dir = st.text_input("Carpeta de red para envío (opcional)", value=os.environ.get("ECHADAS_SALIDA", ""),
                            placeholder=r"\\servidor\imposicion  o  C:\Planos")


# --------------------------------------------------------------------------- #
# Entrada
# --------------------------------------------------------------------------- #
st.title("Generador de echadas Full Color")
st.caption("El motor calcula tiradas, pliegos F/A, LADO 10/13, cuadrantes ALTO/BAJO y la página de cada posición.")

c_tot, c_cfg, c_mb = st.columns([1, 2.6, 1.2])
total = c_tot.number_input("Total de páginas", min_value=4, max_value=400, step=4, value=24)
BOB_OPC = {"Entera": "entera", "Media 24": "media24", "Media 16": "media16"}
bobinas = BOB_OPC[c_mb.selectbox(
    "Bobinas", list(BOB_OPC), index=0,
    help="Entera: tiradas de 32.\n\n"
         "Media 24: F bobina entera + A media banda; tiradas de 24 (24 → F{0-3} + A{0,2}).\n\n"
         "Media 16: F y A en media banda (solo cuadrantes BAJO); tiradas de 16 (16 → F{3,2} + A{3,2}).\n\n"
         "En media banda las tiradas de 8 no llevan REPITE.")]
cfg_text = c_cfg.text_input("Cuerpos, en orden (de afuera hacia adentro)", value=str(total),
                            key=f"cfg_{total}",
                            help="Ejemplos: 24 · 20+4 · 36+24+4+4+4. Cada cuerpo en múltiplos de 4.")

try:
    paginas = parse_config(cfg_text)
except ValueError as ex:
    st.error(str(ex))
    st.stop()
if sum(paginas) != total:
    st.error(f"Los cuerpos suman {sum(paginas)} págs. pero el total indicado es {total}.")
    st.stop()

# editor de cuerpos (nombre + figura)
key = "cuerpos_" + "+".join(map(str, paginas))
df0 = pd.DataFrame({"Cuerpo": nombres_por_defecto(len(paginas)), "Figura": figuras_por_defecto(len(paginas)),
                    "Págs.": paginas})
with st.expander("Cuerpos: nombres y figuras (editable)", expanded=len(paginas) > 1):
    df = st.data_editor(
        df0, key=key, hide_index=True, width="stretch", num_rows="fixed",
        column_config={
            "Cuerpo": st.column_config.TextColumn("Cuerpo", help="Nombre que aparece en el plano"),
            "Figura": st.column_config.SelectboxColumn("Figura", options=FIGURAS, required=True),
            "Págs.": st.column_config.NumberColumn("Págs.", disabled=True),
        })
    tir_txt = st.text_input("Tiradas (opcional, avanzado)", value="",
                            placeholder="Automático: " + "+".join(map(str, plan_tiradas(total, bobinas))),
                            help="Por defecto se llenan tiradas de 32 págs. (24 o 16 en media banda) y la última "
                                 "lleva el resto.")

cuerpos = [Cuerpo(int(r["Págs."]), str(r["Cuerpo"] or f"Cuerpo {i + 1}"), str(r["Figura"]))
           for i, r in df.reset_index(drop=True).iterrows()]
try:
    tiradas = parse_config(tir_txt) if tir_txt.strip() else None
    ech = generar(cuerpos, tiradas, bobinas=bobinas)
except ValueError as ex:
    st.error(str(ex))
    st.stop()

# --------------------------------------------------------------------------- #
# Comparación (opcional)
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Resumen + exportación
# --------------------------------------------------------------------------- #
m = st.columns(4)
m[0].metric("Total", f"{ech.total} págs.")
m[1].metric("Cuerpos", str(len(ech.cuerpos)))
m[2].metric("Tiradas", str(len(ech.tiradas)))
m[2].caption(" | ".join(str(t.paginas) for t in ech.tiradas))
m[3].metric("Pliegos", str(sum(len(t.webs) for t in ech.tiradas)))
if ech.media_banda:
    st.info(f"{BOBINAS[ech.bobinas][0]}: tiradas de hasta {BOBINAS[ech.bobinas][1]} págs. → "
            f"{' | '.join(str(t.paginas) for t in ech.tiradas)}. Las tiradas de 8 no llevan REPITE.")
for a in ech.avisos:
    st.warning(a)

base = safe(f"Echada_{ech.total}p_{ech.config.replace('+', '-')}" + ({"media24": "_MB24", "media16": "_MB16"}.get(ech.bobinas, "")) + (f"_OT{job.orden}" if job.orden else "")
            + f"_{datetime.now():%Y%m%d}")
with st.container(border=True):
    e1, e2, e3 = st.columns([1, 1, 1.4])
    pdf = build_pdf(ech, job, page=pdf_page, orientation=pdf_orient, include_grid=opt_grid,
                    include_signatures=opt_sigs, repite_8=opt_rep)
    xls = build_xlsx(ech, job, include_image=opt_img, repite_8=opt_rep)
    e1.download_button("Descargar PDF para taller", pdf, file_name=f"{base}.pdf", mime="application/pdf",
                       type="primary", width="stretch")
    e2.download_button("Descargar Excel estructurado", xls, file_name=f"{base}.xlsx", width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if e3.button("Enviar a carpeta de red (PDF + Excel)", width="stretch", disabled=not out_dir):
        try:
            dest = Path(out_dir)
            dest.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%H%M%S")
            (dest / f"{base}_{stamp}.pdf").write_bytes(pdf)
            (dest / f"{base}_{stamp}.xlsx").write_bytes(xls)
            st.success(f"Guardado en {dest}")
        except Exception as ex:
            st.error(f"No se pudo guardar en '{out_dir}': {ex}")

# --------------------------------------------------------------------------- #
# Pestañas
# --------------------------------------------------------------------------- #
tab_plan, tab_comp = st.tabs(["Plano generado", "Composición y posiciones"])

with tab_plan:
    for t in reversed(ech.tiradas):
        titulo, detalle = tirada_titulo(ech, t)
        rep = "  ·  REPITE" if (opt_rep and t.puede_repetir) else ""
        st.markdown(f"<div class='band-head'><b>{titulo}{rep}</b><div>{detalle}</div></div>", unsafe_allow_html=True)
        d = tirada_drawing(ech, t, opt_rep)
        st.markdown(f"<div class='plan'>{to_svg(d, max_width=int(d.width * 1.35))}</div>", unsafe_allow_html=True)
    st.caption("Las tiradas se muestran como en las planillas: de la última a la primera (tapa). "
               "ALTO/BAJO = cuadrante · F/A = pliego · LADO 10/13 = caras.")

with tab_comp:
    st.subheader("Composición")
    st.dataframe(pd.DataFrame(composicion(ech)), hide_index=True, width="stretch")
    st.subheader("Posiciones por pliego")
    for t in ech.tiradas:
        for web in t.webs:
            headers, rows = grilla(ech, t.numero, web)
            st.markdown(f"**Tirada {t.numero} · pliego {web}**")
            st.dataframe(pd.DataFrame(rows, columns=headers, index=["Superior", "Inferior"]), width="stretch")
    with st.expander("Tabla completa de posiciones"):
        st.dataframe(pd.DataFrame(posiciones(ech)), hide_index=True, width="stretch")
