#!/usr/bin/env bash
# ==========================================================================
#  Mineral Manager - instala y abre la demo en un solo paso (macOS / Linux)
#  Requiere Python 3.10 o superior.
# ==========================================================================
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d venv ]; then
    echo "[1/4] Creando entorno virtual..."
    "$PY" -m venv venv
fi
source venv/bin/activate

echo "[2/4] Instalando dependencias..."
python -m pip install --disable-pip-version-check -q -r requirements.txt

echo "[3/4] Preparando base de datos y datos de ejemplo..."
python manage.py migrate --noinput -v 0
python manage.py cargar_demo

echo "[4/4] Iniciando en http://127.0.0.1:8000  (usuario: demo / clave: demo1234)"
echo "      Presiona Ctrl+C para detener el servidor."
python manage.py runserver
