# Generador de echadas Full Color (Streamlit)

La app **genera** echadas: usted indica el total de páginas y los cuerpos (por ejemplo `36+24+4+4+4`)
y el motor calcula las tiradas, los pliegos F/A, las caras LADO 10/13, los cuadrantes ALTO/BAJO y la
página de cada posición. No necesita ningún Excel ni base de datos.

## Instalación (una sola vez)
Requiere Python 3.10 o superior.
```bash
cd echadas_app
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
1. **Total de páginas** y **Combinación**: elija una del catálogo estándar o escriba una nueva
   (cuerpos en orden, de afuera hacia adentro, múltiplos de 4).
2. En "Cuerpos" puede renombrar cada cuerpo (Tapa, Suple 1…) y elegir su figura.
3. Exporte PDF para taller o Excel estructurado, o envíe ambos a una carpeta de red.

## Reglas del motor (echadas/generador.py)
- Cada hoja del producto (tira) lleva 4 páginas: en la cara impar p arriba y N+1-p abajo; en la otra
  cara p+1 arriba y N-p abajo.
- Tiradas de 32 págs.; la última lleva el resto. Un cuerpo puede repartirse entre tiradas ("32 de 36").
- Orden de hojas: columnas 3→0; en columnas impares primero pliego F y luego A, en pares A y luego F.
  La página impar va en LADO 10 si la columna es impar, en LADO 13 si es par.
- Columnas usadas por tamaño de tirada: 4→F{3} · 8→F{2,3} · 12→F{2,3}+A{2} · 16→F{0-3} ·
  24→F{0-3}+A{0,2} · 32→F{0-3}+A{0-3}. Hasta 12 págs. se dibuja en medio formato (solo BAJO).
- Tamaños sin formato propio (20, 28) usan el formato siguiente con hojas en blanco y se avisa.
