# Publicar la demo en PythonAnywhere

Guía para publicar Mineral Manager gratis en [PythonAnywhere](https://www.pythonanywhere.com).

Resultado: la app queda en `https://TU-USUARIO.pythonanywhere.com`, siempre encendida y con la cuenta `demo` / `demo1234`. La demo oficial está en <https://jeff017.pythonanywhere.com>.

> Tiempo estimado: 10 minutos. En los comandos, `TU-USUARIO` es tu nombre de usuario de PythonAnywhere.

---

## 1. Crear la cuenta

1. Entra a <https://www.pythonanywhere.com/registration/register/beginner/> y crea una cuenta **Beginner** (gratis, no pide tarjeta).
2. El nombre de usuario será parte del enlace (`TU-USUARIO.pythonanywhere.com`), así que elige uno presentable.

## 2. Descargar el proyecto e instalarlo

En el panel de PythonAnywhere ve a **Consoles → Bash** y pega estos comandos uno por uno:

```bash
git clone https://github.com/y-jeff/Mineral_Manager.git
cd Mineral_Manager
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> Si el repositorio es privado, `git clone` pedirá usuario y contraseña. En la contraseña usa un [token de GitHub](https://github.com/settings/tokens), no tu clave. Lo más simple es hacer el repositorio público.

## 3. Crear el archivo de configuración `.env`

Este comando crea el archivo con una clave secreta nueva y tu dominio ya completado (no hay que editar nada):

```bash
cat > .env <<EOF
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
DJANGO_ALLOWED_HOSTS=$USER.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://$USER.pythonanywhere.com
EOF
```

Comprueba que quedó bien con `cat .env`.

## 4. Preparar la base de datos y los archivos estáticos

```bash
python manage.py migrate
python manage.py cargar_demo
python manage.py collectstatic --noinput
```

## 5. Crear la aplicación web

1. Ve a la pestaña **Web** → **Add a new web app** → **Next**.
2. Elige **Manual configuration** (no la opción "Django") → **Python 3.12** → **Next**.
3. En la página de la app completa estas secciones:

| Sección | Campo | Valor |
|---|---|---|
| **Code** | Source code | `/home/TU-USUARIO/Mineral_Manager` |
| **Code** | Working directory | `/home/TU-USUARIO/Mineral_Manager` |
| **Virtualenv** | Path | `/home/TU-USUARIO/Mineral_Manager/venv` |
| **Static files** | URL / Directory | `/static/` → `/home/TU-USUARIO/Mineral_Manager/staticfiles` |
| **Security** | Force HTTPS | **Enabled** |

4. En **Code**, haz clic en el enlace del **WSGI configuration file**, borra todo su contenido y pega esto (cambia `TU-USUARIO`):

```python
import os
import sys

proyecto = '/home/TU-USUARIO/Mineral_Manager'
if proyecto not in sys.path:
    sys.path.insert(0, proyecto)

os.environ['DJANGO_SETTINGS_MODULE'] = 'MineralManager.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

   Guarda con **Save**. La configuración (clave, dominio) se lee del archivo `.env` del paso 3.

5. Vuelve a la pestaña **Web** y presiona el botón verde **Reload**.
6. Abre `https://TU-USUARIO.pythonanywhere.com` y entra con `demo` / `demo1234`.

## 6. Restaurar los datos de la demo

Si un visitante borra o cambia datos, este comando deja la demo limpia y con las fechas de las certificaciones actualizadas. Ejecútalo en una consola **Bash**:

```bash
cd ~/Mineral_Manager && venv/bin/python manage.py cargar_demo --reset
```

> Las cuentas gratuitas creadas desde enero de 2026 no incluyen tareas programadas. En una cuenta pagada (o antigua) puedes automatizarlo en la pestaña **Tasks** con el comando `cd /home/TU-USUARIO/Mineral_Manager && venv/bin/python manage.py cargar_demo --reset`.

## 7. Mantenerla encendida

En el plan gratuito la app se desactiva si no la renuevas cada **mes**. PythonAnywhere te avisa por correo una semana antes: entra a la pestaña **Web** y presiona **Run until 1 month from today**.

---

## Actualizar la demo después de cambios en GitHub

```bash
cd ~/Mineral_Manager
source venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Luego presiona **Reload** en la pestaña **Web**.

## Si algo falla

El detalle del error está en la pestaña **Web → Log files → Error log**.

| Síntoma | Causa probable |
|---|---|
| "Something went wrong" o error 500 | Revisa el Error log. Si dice `ImproperlyConfigured`, falta el archivo `.env` (paso 3). |
| `Bad Request (400)` | El dominio en `DJANGO_ALLOWED_HOSTS` del `.env` no coincide con tu dirección. |
| La página se ve sin estilos | Falta `collectstatic` (paso 4) o el mapeo de **Static files** (paso 5). |
| Error `403 CSRF` al iniciar sesión | Revisa `DJANGO_CSRF_TRUSTED_ORIGINS` en el `.env` (debe empezar con `https://`). |

> En el plan gratuito el envío de correos está bloqueado, por lo que "¿Olvidaste tu contraseña?" no enviará mensajes. No afecta a la demo.
