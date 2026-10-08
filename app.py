"""
Generador de echadas Full Color — imposición offset (rotativa)
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
from echadas.generador import (BOBINAS, FIGURAS, Cuerpo, figuras_por_defecto, generar, parse_config,
                               parse_enteras, plan_tiradas)
from echadas.pdf import Job, build_pdf
from echadas.render import to_svg
from echadas.tablas import composicion, grilla, posiciones

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / ".cache"

ASSETS = APP_DIR / "assets"
LOGO = ASSETS / "logo.png"


def _b64(path: Path) -> str:
    import base64
    try:
        return base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""


LOGO_B64 = _b64(LOGO)

st.set_page_config(page_title="Generador de echadas", page_icon=str(ASSETS / "icono.png") if LOGO_B64 else None,
                   layout="wide", initial_sidebar_state="expanded")
if LOGO_B64:
    st.logo(str(LOGO), size="large")

# ---------------------------------------------------------------- estilo (solo look & feel)
_CSS = """
<style>
  :root {
    --verde: #077C50; --verde-2: #0A9A63; --teal: #3AB3C4; --tinta: #14211C; --gris: #5D6B66;
    --borde: rgba(20, 33, 28, .09); --sombra: 0 1px 2px rgba(16,24,40,.04), 0 6px 18px rgba(16,24,40,.06);
  }
  .stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(58,179,196,.10), transparent 60%),
                       radial-gradient(900px 400px at -10% 0%, rgba(7,124,80,.08), transparent 55%), #F6F8F7; }
  .block-container { padding-top: 1.4rem; padding-bottom: 1rem; max-width: 1480px; }
  header[data-testid="stHeader"] { background: transparent; }

  /* ---------- encabezado ---------- */
  .hero { display:flex; align-items:center; gap:18px; padding: 18px 22px; margin-bottom: 18px;
          background: linear-gradient(120deg, #075C3E 0%, var(--verde) 45%, #1E9AA8 100%);
          border-radius: 18px; color: #fff; box-shadow: 0 10px 30px rgba(7,124,80,.22); position: relative;
          overflow: hidden; }
  .hero::after { content:""; position:absolute; right:-60px; top:-60px; width:240px; height:240px;
                 border-radius:50%; background: rgba(255,255,255,.07); }
  .hero .badge { width:62px; height:62px; flex:0 0 62px; border-radius:16px; background:#fff;
                 display:flex; align-items:center; justify-content:center; box-shadow: 0 4px 14px rgba(0,0,0,.15); }
  .hero .badge img { width:48px; height:48px; }
  .hero h1 { color:#fff !important; font-size: 1.75rem !important; font-weight: 800 !important; margin: 0 !important;
             padding: 0 !important; letter-spacing: -.02em; line-height: 1.15; }
  .hero p { margin: 4px 0 0; opacity: .88; font-size: .93rem; }
  .hero .chips { margin-left:auto; display:flex; gap:8px; flex-wrap:wrap; z-index:1; }
  .hero .chip { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25); color:#fff;
                padding: 5px 12px; border-radius: 999px; font-size: .78rem; font-weight: 600; white-space: nowrap; }

  /* ---------- tarjetas / contenedores ---------- */
  div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px !important; }
  div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div[data-testid="stVerticalBlock"]) {
      background: #fff; border: 1px solid var(--borde) !important; box-shadow: var(--sombra); }
  .seccion { font-size:.74rem; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color: var(--verde);
             margin: 2px 0 6px; }

  /* ---------- inputs ---------- */
  div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] {
      border-radius: 10px !important; border-color: rgba(20,33,28,.14) !important; background: #fff; }
  div[data-baseweb="input"]:focus-within, div[data-baseweb="select"] > div:focus-within {
      border-color: var(--verde) !important; box-shadow: 0 0 0 3px rgba(7,124,80,.14) !important; }
  label p { font-weight: 600 !important; color: var(--tinta) !important; font-size: .86rem !important; }

  /* ---------- métricas ---------- */
  div[data-testid="stMetric"] { min-height: 132px; background:#fff; border:1px solid var(--borde); border-radius:14px;
      padding: 14px 16px; box-shadow: var(--sombra); position: relative; overflow: hidden; }
  div[data-testid="stMetric"]::before { content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
      background: linear-gradient(180deg, var(--verde), var(--teal)); }
  div[data-testid="stMetricLabel"] p { color: var(--gris) !important; font-size: .78rem !important;
      text-transform: uppercase; letter-spacing: .06em; font-weight: 600 !important; }
  div[data-testid="stMetricValue"] { font-weight: 800; color: var(--tinta); }

  /* ---------- botones ---------- */
  .stButton > button, .stDownloadButton > button { border-radius: 11px !important; font-weight: 600 !important;
      padding: .55rem 1rem !important; transition: transform .08s ease, box-shadow .15s ease; }
  .stDownloadButton > button[kind="primary"], .stButton > button[kind="primary"] {
      background: linear-gradient(120deg, var(--verde), var(--verde-2)) !important; border: 0 !important;
      box-shadow: 0 6px 16px rgba(7,124,80,.25); }
  .stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); }

  /* ---------- pestañas ---------- */
  div[role="tablist"] { gap: 6px; background: rgba(20,33,28,.05); padding: 5px; border-radius: 12px;
      width: fit-content; border: 0 !important; }
  div[data-testid="stTab"] { border-radius: 9px; padding: 7px 16px !important; }
  div[data-testid="stTab"][aria-selected="true"] { background: #fff; box-shadow: var(--sombra); }
  div[data-testid="stTab"] p { font-weight: 600 !important; }
  div[role="tablist"] .react-aria-SelectionIndicator { display: none; }
  /* ---------- barra lateral ---------- */
  section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--borde); }
  section[data-testid="stSidebar"] h2 { font-size: .78rem !important; text-transform: uppercase; letter-spacing: .09em;
      color: var(--verde) !important; font-weight: 700 !important; margin-top: .4rem; }

  /* ---------- alertas, expander, tablas ---------- */
  div[data-testid="stAlert"] { border-radius: 12px; }
  div[data-testid="stAlertContentInfo"] { color: #0B5F63; }
  div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) > div { background: rgba(58,179,196,.12) !important; }
  details { border-radius: 14px !important; border: 1px solid var(--borde) !important; background: #fff; }
  div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid var(--borde); }

  /* ---------- planos ---------- */
  .band-head { display:flex; align-items:center; gap: 12px; background:#fff; border:1px solid var(--borde);
               border-radius: 14px 14px 0 0; padding: .7rem 1rem; margin: 1.2rem 0 0; box-shadow: var(--sombra); }
  .band-head .num { width:34px; height:34px; border-radius:10px; flex:0 0 34px; display:flex; align-items:center;
                    justify-content:center; font-weight:800; color:#fff;
                    background: linear-gradient(135deg, var(--verde), var(--teal)); }
  .band-head b { font-size: 1rem; color: var(--tinta); } .band-head div.det { color: var(--gris); font-size:.83rem; }
  .band-head .tag { margin-left:auto; font-size:.72rem; font-weight:700; padding:4px 10px; border-radius:999px;
                    background: rgba(58,179,196,.14); color:#137F8D; white-space:nowrap; }
  .band-head .tag.rep { background: rgba(230,126,34,.14); color:#B35C0F; }
  .plan { background:#fff; border:1px solid var(--borde); border-top:0; border-radius: 0 0 14px 14px; padding: 14px;
          overflow-x:auto; box-shadow: var(--sombra); }

  /* ---------- pie ---------- */
  .pie { margin-top: 36px; padding: 18px 0 6px; border-top: 1px solid var(--borde); display:flex;
         align-items:center; justify-content:center; gap:10px; color: var(--gris); font-size:.85rem; }
  .pie img { width:26px; height:26px; }
  .pie b { color: var(--verde); font-weight:700; letter-spacing:.01em; }
</style>
"""
# sin líneas en blanco: el markdown cortaría el bloque <style> y mostraría el CSS como texto
st.markdown("\n".join(l for l in _CSS.splitlines() if l.strip()), unsafe_allow_html=True)


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
_logo_html = f"<div class='badge'><img src='data:image/png;base64,{LOGO_B64}'/></div>" if LOGO_B64 else ""
st.markdown(f"""
<div class="hero">
  {_logo_html}
  <div>
    <h1>Generador de echadas Full Color</h1>
    <p>Imposición offset · tiradas, pliegos F/A, LADO 10/13, cuadrantes ALTO/BAJO y página de cada posición.</p>
  </div>
  <div class="chips"><span class="chip">Rotativa</span></div>
</div>
""", unsafe_allow_html=True)

entrada = st.container(border=True)
entrada.markdown("<div class='seccion'>Configuración de la echada</div>", unsafe_allow_html=True)
c_tot, c_cfg, c_mb = entrada.columns([1, 2.6, 1.2])
total = c_tot.number_input("Total de páginas", min_value=4, max_value=400, step=4, value=24)
BOB_OPC = {"Entera": "entera", "Media 24": "media24", "Media 16": "media16", "Combinada": "combinada"}
bob_sel = BOB_OPC[c_mb.selectbox(
    "Bobinas", list(BOB_OPC), index=0,
    help="Entera: tiradas de 32.\n\n"
         "Media 24: F bobina entera + A media banda; tiradas de 24 (24 → F{0-3} + A{0,2}).\n\n"
         "Media 16: F y A en media banda (solo cuadrantes BAJO); tiradas de 16 (16 → F{3,2} + A{3,2}).\n\n"
         "Combinada: las tiradas que indique van en banda entera (32) y el resto en Media 24 o Media 16.\n\n"
         "En media banda las tiradas de 8 no llevan REPITE.")]
enteras = ()
bobinas = bob_sel
if bob_sel == "combinada":
    k1, k2, _ = entrada.columns([1.2, 1.2, 2.2])
    ent_txt = k1.text_input("Tiradas en banda entera", value="1",
                            help="Número de tirada (1 = tapa). Varias separadas por coma: 1,3")
    bobinas = {"Media 24": "media24", "Media 16": "media16"}[k2.selectbox(
        "Resto en", ["Media 24", "Media 16"], help="Tipo de media banda para las demás tiradas.")]
    try:
        enteras = parse_enteras(ent_txt)
    except ValueError as ex:
        st.error(str(ex))
        st.stop()
    if not enteras:
        st.error("Combinada: indique al menos una tirada en banda entera (por ejemplo 1).")
        st.stop()
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
with entrada.expander("Cuerpos: nombres y figuras (editable)", expanded=len(paginas) > 1):
    df = st.data_editor(
        df0, key=key, hide_index=True, width="stretch", num_rows="fixed",
        column_config={
            "Cuerpo": st.column_config.TextColumn("Cuerpo", help="Nombre que aparece en el plano"),
            "Figura": st.column_config.SelectboxColumn("Figura", options=FIGURAS, required=True),
            "Págs.": st.column_config.NumberColumn("Págs.", disabled=True),
        })
    tir_txt = st.text_input("Tiradas (opcional, avanzado)", value="",
                            placeholder="Automático: " + "+".join(map(str, plan_tiradas(total, bobinas, enteras))),
                            help="Por defecto se llenan tiradas de 32 págs. (24 o 16 en media banda; en combinada "
                                 "cada tirada según su bobina) y la última "
                                 "lleva el resto.")

cuerpos = [Cuerpo(int(r["Págs."]), str(r["Cuerpo"] or f"Cuerpo {i + 1}"), str(r["Figura"]))
           for i, r in df.reset_index(drop=True).iterrows()]
try:
    tiradas = parse_config(tir_txt) if tir_txt.strip() else None
    ech = generar(cuerpos, tiradas, bobinas=bobinas, enteras=enteras)
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
m[2].metric("Tiradas", str(len(ech.tiradas)), delta=" | ".join(str(t.paginas) for t in ech.tiradas),
            delta_color="off", delta_arrow="off")
m[3].metric("Pliegos", str(sum(len(t.webs) for t in ech.tiradas)))
if ech.media_banda:
    detalle_t = " | ".join(f"{t.paginas}{' (entera)' if ech.combinada and t.bobinas == 'entera' else ''}"
                           for t in ech.tiradas)
    st.info(f"{ech.descripcion_bobinas} → {detalle_t}. En media banda las tiradas de 8 no llevan REPITE.")
for a in ech.avisos:
    st.warning(a)

base = safe(f"Echada_{ech.total}p_{ech.config.replace('+', '-')}" + (("_COMB" if ech.combinada else "_MB") + ech.bobinas[-2:] if ech.media_banda else "") + (f"_OT{job.orden}" if job.orden else "")
            + f"_{datetime.now():%Y%m%d}")
with st.container(border=True):
    st.markdown("<div class='seccion'>Exportar</div>", unsafe_allow_html=True)
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
        tags = ""
        if t.media_banda:
            tags += f"<span class='tag'>MEDIA BANDA {t.bobinas[-2:]}</span>"
        elif ech.combinada:
            tags += "<span class='tag'>BANDA ENTERA</span>"
        if opt_rep and t.puede_repetir:
            tags += "<span class='tag rep'>REPITE</span>"
        tit = titulo.replace(" · MEDIA BANDA 24", "").replace(" · MEDIA BANDA 16", "").replace(" · BANDA ENTERA", "")
        st.markdown(f"<div class='band-head'><span class='num'>{t.numero}</span><div><b>{tit}</b>"
                    f"<div class='det'>{detalle}</div></div>{tags}</div>", unsafe_allow_html=True)
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

# --------------------------------------------------------------------------- #
# Pie
# --------------------------------------------------------------------------- #
_pie_logo = f"<img src='data:image/png;base64,{LOGO_B64}'/>" if LOGO_B64 else ""
st.markdown(f"<div class='pie'>{_pie_logo}<span>Generador de echadas Full Color · by <b>nosotros</b></span></div>",
            unsafe_allow_html=True)
