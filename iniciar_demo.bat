@echo off
REM ==========================================================================
REM  Mineral Manager - instala y abre la demo en un solo paso (Windows)
REM  Requiere Python 3.10 o superior: https://www.python.org/downloads/
REM ==========================================================================
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist venv (
    echo [1/4] Creando entorno virtual...
    %PY% -m venv venv || goto error
)
call venv\Scripts\activate.bat

echo [2/4] Instalando dependencias...
python -m pip install --disable-pip-version-check -q -r requirements.txt || goto error

echo [3/4] Preparando base de datos y datos de ejemplo...
python manage.py migrate --noinput -v 0 || goto error
python manage.py cargar_demo || goto error

echo [4/4] Iniciando en http://127.0.0.1:8000  (usuario: demo / clave: demo1234)
echo       Cierra esta ventana o presiona Ctrl+C para detener el servidor.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
python manage.py runserver
goto :eof

:error
echo.
echo Ocurrio un error. Revisa el mensaje de arriba.
pause
