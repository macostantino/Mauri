# Generador de echadas Full Color (Streamlit)

La app **genera** echadas: usted indica el total de páginas y los cuerpos (por ejemplo `36+24+4+4+4`)
y el motor calcula las tiradas, los pliegos F/A, las caras LADO 10/13, los cuadrantes ALTO/BAJO y la
página de cada posición. No necesita ningún Excel ni base de datos.

## Instalación (una sola vez)
Requiere Python 3.10 o superior.
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      Linux/Mac:  source .venv/bin/activate
pip install -r requirements.txt
```
En Windows alcanza con doble clic en `iniciar.bat`.

## Ejecutar
```bash
streamlit run app.py
```
Para usarla desde otras PCs: `streamlit run app.py --server.address 0.0.0.0` → `http://IP-de-la-PC:8501`.

## Uso
1. **Total de páginas** y **Cuerpos**: escriba los cuerpos en orden, de afuera hacia adentro,
   separados por "+" (por ejemplo 4+4+4+4). Cada cuerpo en múltiplos de 4 y la suma igual al total.
2. En "Cuerpos" puede renombrar cada cuerpo (Tapa, Suple 1…) y elegir su figura.
3. **Bobinas** (selector junto a los cuerpos): Entera (tiradas de 32), Media 24 (F entera + A media
   banda, tiradas de 24), Media 16 (F y A en media banda, solo BAJO, tiradas de 16) o Combinada
   (las tiradas que indique van en banda entera de 32 y el resto en Media 24 o Media 16).
4. Exporte PDF para taller o Excel estructurado.

## Reglas del motor (echadas/generador.py)
- Cada hoja del producto (tira) lleva 4 páginas: en la cara impar p arriba y N+1-p abajo; en la otra
  cara p+1 arriba y N-p abajo.
- Tiradas de 32 págs.; la última lleva el resto. Un cuerpo puede repartirse entre tiradas ("32 de 36").
- Orden de hojas: columnas 3→0; en columnas impares primero pliego F y luego A, en pares A y luego F.
  La página impar va en LADO 10 si la columna es impar, en LADO 13 si es par.
- Columnas usadas por tamaño de tirada: 4→F{3} · 8→F{2,3} · 12→F{2,3}+A{2} · 16→F{0-3} ·
  24→F{0-3}+A{0,2} · 32→F{0-3}+A{0-3}. Hasta 12 págs. se dibuja en medio formato (solo BAJO).
- Tamaños sin formato propio (20, 28) usan el formato siguiente con hojas en blanco y se avisa.
- **Bobinas** (selector): *Media 24* = F entera + A media banda; mismos formatos que banda entera hasta
  24 (24→F{0-3}+A{0,2}), tiradas de 24. *Media 16* = F y A en media banda, solo columnas BAJO:
  4→F{3} · 8→F{2,3} · 12→F{2,3}+A{2} · 16→F{2,3}+A{2,3}, tiradas de 16. En ambos la última tirada lleva
  el resto, el orden de hojas y caras es el mismo y las tiradas de 8 no llevan REPITE.
- **Combinada**: se indican los números de tirada en banda entera (ej. `1` o `1,3`) y el tipo de media
  banda para las demás. Cada tirada toma su máximo (32 o 24/16) en orden y la última lleva el resto
  (ej. 80 págs., entera la 1, resto Media 24 → 32 | 24 | 24).

## Apariencia
- Tema y colores: `.streamlit/config.toml` (verde #077C50 / turquesa #3AB3C4). Fuente Inter (si no hay internet,
  usa la fuente del sistema).
- Logo: `assets/logo.png` (encabezado, barra lateral y pie) y `assets/icono.png` (pestaña del navegador).
