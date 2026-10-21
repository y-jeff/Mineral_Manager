# Historial de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [versionado semántico](https://semver.org/lang/es/).

## [2.0.0] - 2026-10-20

### Agregado
- Rediseño visual completo: plantilla base con menú lateral, tema propio, íconos y diseño adaptable a celulares.
- Panel principal con gráficos (Chart.js), certificaciones por vencer y artículos para reponer.
- Cuenta y datos de demostración con `python manage.py cargar_demo`, y scripts `iniciar_demo.bat` / `iniciar_demo.sh` para instalar y abrir la app en un paso.
- Carga masiva desde Excel (una hoja por tabla, todo o nada) además de CSV, con Excel de ejemplo descargable.
- Creación de nuevos tipos de certificación desde la pantalla de trabajadores.
- 20 pruebas automáticas y ejecución en GitHub Actions (Python 3.10, 3.12 y 3.14).
- README con capturas, guía de instalación y formato de carga.

### Cambiado
- Actualización a Django 5.2 LTS (compatible con Python 3.10 a 3.14).
- Credenciales de correo y `SECRET_KEY` se leen desde variables de entorno.
- Zona horaria `America/Santiago`.
- `requirements.txt` reducido a las dependencias que usa el proyecto.
- Código documentado (docstrings en vistas y modelos) y vistas agrupadas por módulo.

### Corregido
- Los traspasos de bodega a pañol descontaban stock de bodega pero no lo sumaban al pañol.
- "Registrar mantenimiento" enviaba el formulario a la ruta de trabajos.
- Registrar y ver trabajos de maquinaria fallaba por un campo inexistente (`fecha_trabajo`).
- La búsqueda en el historial de mantenimientos fallaba.
- "Agregar trabajador" no guardaba las certificaciones ingresadas.
- Editar un trabajador cambiaba su turno, jornada y horario a la primera opción.
- Los RUT terminados en K no se aceptaban al agregar un trabajador, y los RUT se guardaban sin guion.
- Dar de baja trabajadores no exigía sesión ni token CSRF.
- Los historiales de maquinaria podían verse sin iniciar sesión.
- `create_superuser` fallaba por una variable no definida.
- La app no iniciaba en sistemas sin el locale `es_ES.UTF-8`.

### Eliminado
- Base de datos, archivos subidos y `__pycache__` del repositorio.
- Hojas de estilo, scripts y vistas sin uso.

## [1.0.0] - 2024-12

Versión inicial: gestión de trabajadores, certificaciones, maquinaria, bodega, pañol, retiros y carga de archivos CSV.
