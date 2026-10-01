@echo off
REM Lanzador para Windows: la primera vez crea el entorno e instala todo; despues abre la app.
cd /d "%~dp0"

where python 1>NUL 2>NUL
if errorlevel 1 (
  echo No se encontro Python. Instalelo desde https://www.python.org marcando "Add Python to PATH".
  pause
  exit /b 1
)

if not exist .venv\instalado.txt (
  echo Primera ejecucion: instalando dependencias, puede tardar unos minutos...
  if not exist .venv python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Fallo la instalacion. Revise la conexion a internet y vuelva a ejecutar.
    pause
    exit /b 1
  )
  echo ok> .venv\instalado.txt
) else (
  call .venv\Scripts\activate.bat
)

echo Abriendo la app en el navegador (no cierre esta ventana mientras la usa)...
streamlit run app.py
pause
