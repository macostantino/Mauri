@echo off
REM Lanzador para Windows: crea el entorno la primera vez y abre la app.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
streamlit run app.py
