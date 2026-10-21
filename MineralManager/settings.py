"""
Configuración de Django para Mineral Manager.

En desarrollo funciona sin configurar nada. En producción los valores se leen desde
variables de entorno o desde un archivo .env en la raíz del proyecto (ver .env.example
y DEPLOY.md).
"""
import os
from pathlib import Path

from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga el archivo .env si existe (en el servidor; en local es opcional)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass


def env_bool(nombre, por_defecto):
    """Lee una variable de entorno como booleano ("True"/"False")."""
    return os.environ.get(nombre, str(por_defecto)).strip().lower() in ('1', 'true', 'yes', 'si', 'sí')


def env_lista(nombre, por_defecto=''):
    """Lee una variable de entorno con valores separados por coma."""
    return [valor.strip() for valor in os.environ.get(nombre, por_defecto).split(',') if valor.strip()]


# -----------------------------------------------------------------------------
# Seguridad
# -----------------------------------------------------------------------------
DEBUG = env_bool('DJANGO_DEBUG', True)

CLAVE_DESARROLLO = 'django-insecure-solo-para-desarrollo-local'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', CLAVE_DESARROLLO)
if not DEBUG and SECRET_KEY == CLAVE_DESARROLLO:
    raise ImproperlyConfigured('Define DJANGO_SECRET_KEY para ejecutar con DJANGO_DEBUG=False.')

ALLOWED_HOSTS = env_lista('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_lista('DJANGO_CSRF_TRUSTED_ORIGINS')

# En producción (HTTPS) las cookies de sesión solo viajan cifradas
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env_bool('DJANGO_HTTPS', not DEBUG)


# -----------------------------------------------------------------------------
# Aplicación
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'MineralApp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'MineralManager.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'MineralApp.context_processors.navegacion',  # Menú lateral de base.html
            ],
        },
    },
]

WSGI_APPLICATION = 'MineralManager.wsgi.application'

AUTH_USER_MODEL = 'MineralApp.CustomUser'
LOGIN_URL = 'login_signup'
EMAIL_CONFIRMATION_REQUIRED = False

# Usa las clases de alerta de Bootstrap para los mensajes de Django (error -> alert-danger)
MESSAGE_TAGS = {message_constants.ERROR: 'danger'}


# -----------------------------------------------------------------------------
# Base de datos
# -----------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('DJANGO_DB_PATH', BASE_DIR / 'db.sqlite3'),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# -----------------------------------------------------------------------------
# Idioma y zona horaria
# -----------------------------------------------------------------------------
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Archivos estáticos y subidos
# -----------------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Destino de `collectstatic` en producción

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# -----------------------------------------------------------------------------
# Correo (recuperación de contraseña)
# -----------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')  # Contraseña de aplicación de Gmail
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
