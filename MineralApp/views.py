"""
Vistas de Mineral Manager.

Secciones:
  - Acceso y panel principal
  - Carga masiva de datos (CSV y Excel)
  - Inventario: pañol, bodega, traspasos y retiros
  - Trabajadores y certificaciones
  - Maquinaria: estado, mantenimientos y trabajos
"""
# Biblioteca estándar
import csv
import json
from datetime import datetime, timedelta
from io import BytesIO

# Django
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import now

# Terceros
import chardet
from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

# Proyecto
from .demo import construir_libro
from .forms import ArticuloBodegaForm, ArticuloPanolForm, RetiroArticuloForm
from .models import (
    Area, ArticuloBodega, ArticuloPanol, Bodega, Capacitacion, CapacitacionTrabajador, Cargo,
    CustomUser, Horario, Jornada, MantenimientoMaquinaria, Maquinaria, MovimientoArticulo, Panol,
    RegistroHoras, RetiroArticulo, Trabajador, TrabajoMaquinaria, Turno,
)


# =============================================================================
# Acceso y panel principal
# =============================================================================

def login_signup_view(request):
    """
    Inicio de sesión. Si el usuario ya está autenticado, lo envía al panel principal.
    Si existe la cuenta de demostración, el formulario muestra sus credenciales.
    """
    if request.user.is_authenticated:
        return redirect('home')

    contexto = {'demo_disponible': CustomUser.objects.filter(username='demo', is_active=True).exists()}

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is None:
            contexto['error'] = 'Nombre de usuario o contraseña incorrectos.'
        elif not user.email_confirmed and settings.EMAIL_CONFIRMATION_REQUIRED:
            contexto['error'] = 'Su cuenta no ha sido confirmada.'
        else:
            login(request, user)
            return redirect('home')

    return render(request, 'login.html', contexto)


@login_required
def index(request):
    """
    Panel principal: indicadores, gráficos, certificaciones por vencer y artículos para reponer.
    """
    total_trabajadores = Trabajador.objects.filter(activo=True).count()
    stock_bajo_panol = ArticuloPanol.objects.filter(cantidad__lte=50).count()
    stock_bajo_bodega = ArticuloBodega.objects.filter(cantidad__lte=50).count()

    # Obtener certificaciones próximas a expirar (90 días o menos) o expiradas
    certificaciones_proximas_qs = CapacitacionTrabajador.objects.filter(
        Q(fecha_fin__lte=now() + timedelta(days=90), fecha_fin__gte=now()) |
        Q(fecha_fin__lt=now()),
        trabajador__activo=True
    ).select_related('trabajador', 'capacitacion')

    certificaciones_data = [
        {
            "trabajador": cert.trabajador,
            "capacitacion": cert.capacitacion,
            "fecha_fin": cert.fecha_fin,
            "dias_restantes": (cert.fecha_fin - now().date()).days if cert.fecha_fin >= now().date() else "Expirada",
        }
        for cert in certificaciones_proximas_qs
    ]

    maquinaria_mantenimiento = Maquinaria.objects.filter(estado="En Mantenimiento").count()
    maquinaria_inactiva = Maquinaria.objects.filter(estado="Inactivo").count()

    # Datos para los gráficos del panel (se pasan al template como JSON con json_script)
    trabajadores_por_area = (
        Trabajador.objects.filter(activo=True)
        .values('area__nombre_area').annotate(total=Count('rut')).order_by('-total')
    )
    maquinaria_por_estado = Maquinaria.objects.values('estado').annotate(total=Count('id')).order_by('estado')
    graficos = {
        'areas': {
            'labels': [fila['area__nombre_area'] for fila in trabajadores_por_area],
            'valores': [fila['total'] for fila in trabajadores_por_area],
        },
        'maquinaria': {
            'labels': [fila['estado'] for fila in maquinaria_por_estado],
            'valores': [fila['total'] for fila in maquinaria_por_estado],
        },
    }

    # Artículos con menos stock entre bodega y pañol (para la lista de reposición)
    reposicion = sorted(
        [{'nombre': a.nombre_articulo, 'ubicacion': a.panol.nombre_panol, 'cantidad': a.cantidad}
         for a in ArticuloPanol.objects.filter(cantidad__lte=10).select_related('panol')] +
        [{'nombre': a.nombre_articulo, 'ubicacion': a.bodega.nombre_bodega, 'cantidad': a.cantidad}
         for a in ArticuloBodega.objects.filter(cantidad__lte=10).select_related('bodega')],
        key=lambda articulo: articulo['cantidad'],
    )[:6]

    context = {
        "total_trabajadores": total_trabajadores,
        "total_maquinaria": Maquinaria.objects.count(),
        "stock_bajo_panol": stock_bajo_panol,
        "stock_bajo_bodega": stock_bajo_bodega,
        "certificaciones_proximas": len(certificaciones_data),
        "certificaciones_data": sorted(certificaciones_data, key=lambda c: c["fecha_fin"]),
        "maquinaria_mantenimiento": maquinaria_mantenimiento,
        "maquinaria_inactiva": maquinaria_inactiva,
        "graficos": graficos,
        "reposicion": reposicion,
    }

    return render(request, "index.html", context)


# =============================================================================
# Carga masiva de datos (CSV y Excel)
# =============================================================================


def decode_csv_file(file):
    """
    Decodifica el archivo CSV con la codificación detectada.
    """
    raw_data = file.read()
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    decoded_file = raw_data.decode(encoding).splitlines()
    return csv.DictReader(decoded_file)


def procesar_archivo_csv(nombre_archivo, file):
    """
    Identifica el archivo CSV y llama a la función de procesamiento correspondiente.
    """
    reader = decode_csv_file(file)
    procesar_tabla(nombre_archivo, reader.fieldnames, reader)


def valor_celda(valor):
    """
    Convierte el valor de una celda de Excel al mismo texto que tendría en un CSV.
    """
    if valor is None:
        return ''
    if isinstance(valor, datetime):
        if valor.hour or valor.minute:
            return valor.strftime("%Y-%m-%d %H:%M")
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def procesar_archivo_excel(nombre_archivo, file):
    """
    Procesa cada hoja del Excel como si fuera un CSV independiente, en el orden del libro.
    Si una hoja falla, no se guarda nada (transacción).
    """
    libro = load_workbook(file, data_only=True, read_only=True)
    with transaction.atomic():
        for hoja in libro.worksheets:
            if hoja.title.lower().startswith('instrucciones'):
                continue
            filas = [[valor_celda(v) for v in fila] for fila in hoja.iter_rows(values_only=True)]
            filas = [f for f in filas if any(f)]
            if not filas:
                continue
            columnas = filas[0]
            datos = [dict(zip(columnas, f)) for f in filas[1:]]
            procesar_tabla(f"{nombre_archivo} › {hoja.title}", columnas, datos)


def procesar_tabla(nombre_archivo, columnas, reader):
    """
    Identifica el tipo de tabla según sus columnas y llama a la función de procesamiento correspondiente.
    """
    try:
        if 'RUT' in columnas and 'Nombre' in columnas and 'Area' in columnas:
            procesar_trabajadores_csv(reader)
        elif 'Código' in columnas and 'Nombre Maquinaria' in columnas:
            procesar_maquinarias_csv(reader)
        elif 'Bodega' in columnas:
            procesar_inventario_bodega_csv(reader)
        elif 'Pañol' in columnas:
            procesar_inventario_panol_csv(reader)
        elif 'Capacitacion' in columnas and 'Fecha Inicio' in columnas:
            procesar_capacitaciones_csv(reader)  # Agregado para Capacitaciones.csv
        elif 'Código' in columnas and 'Fecha Mantenimiento' in columnas:
            procesar_mantenimientos_csv(reader)
        elif 'Código' in columnas and 'Fecha Inicio' in columnas and 'Fecha Fin' in columnas:
            procesar_trabajos_maquinaria_csv(reader)
        else:
            raise Exception(f"El archivo {nombre_archivo} no es reconocido o tiene formato incorrecto.")
    except Exception as e:
        raise e

        

@login_required
def upload_csv(request):
    """
    Vista principal para manejar la subida de archivos CSV o Excel (.xlsx).
    """
    if request.method == 'POST' and 'file' in request.FILES:
        archivo = request.FILES['file']
        try:
            if archivo.name.lower().endswith('.xlsx'):
                procesar_archivo_excel(archivo.name, archivo)
            else:
                procesar_archivo_csv(archivo.name, archivo)
            messages.success(request, "Subida con éxito.")  # Mensaje directo
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect('upload_csv')  # Redirige para refrescar la página

    return render(request, 'upload.html')


@login_required
def descargar_excel_ejemplo(request):
    """
    Descarga el Excel de demostración (MineralApp/demo.py) generado con las fechas de hoy.
    """
    archivo = BytesIO()
    construir_libro().save(archivo)
    return HttpResponse(
        archivo.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="MineralManager_Datos_Prueba.xlsx"'},
    )


# Funciones de procesamiento: una por tipo de tabla. Reciben las filas como diccionarios.

def procesar_trabajadores_csv(reader):
    """
    Procesa el archivo Trabajadores.csv y crea o actualiza trabajadores y sus horas.
    """
    for row in reader:
        try:
            # Obtener o crear los campos relacionados
            area, _ = Area.objects.get_or_create(nombre_area=row['Area'])
            turno, _ = Turno.objects.get_or_create(tipo_turno=row['Turno'])
            jornada, _ = Jornada.objects.get_or_create(tipo_jornada=row['Jornada'])
            cargo, _ = Cargo.objects.get_or_create(nombre_cargo=row['Cargo'])
            horario, _ = Horario.objects.get_or_create(ciclo=row.get('Horario', 'Sin Definir'))

            # Crear o actualizar Trabajador
            trabajador, _ = Trabajador.objects.update_or_create(
                rut=row['RUT'],
                defaults={
                    'nombre_trabajador': row['Nombre'],
                    'area': area,
                    'turno': turno,
                    'jornada': jornada,
                    'cargo': cargo,
                    'horario': horario,
                }
            )

            # Registrar horas esperadas y trabajadas
            RegistroHoras.objects.update_or_create(
                trabajador=trabajador,
                fecha_registro=timezone.now().date(),
                defaults={
                    'area': trabajador.area,  # Asignar el área desde el trabajador
                    'horas_esperadas': int(row['Horas Esperadas']),
                    'horas_trabajadas': int(row['Horas']),
                }
            )
        except Exception as e:
            raise Exception(f"Error al procesar trabajador RUT {row['RUT']}: {e}")


def procesar_maquinarias_csv(reader):
    """
    Procesa el archivo Maquinarias.csv.
    """
    for row in reader:
        area, _ = Area.objects.get_or_create(nombre_area=row['Area'])
        Maquinaria.objects.update_or_create(
            codigo_maquinaria=row['Código'],
            defaults={
                'nombre_maquinaria': row['Nombre Maquinaria'],
                'fecha_adquisicion': datetime.strptime(row['Fecha Adquisición'], "%Y-%m-%d").date(),
                'estado': row['Estado'],
                'area': area,
            }
        )

def procesar_inventario_panol_csv(reader):
    """
    Procesa el archivo Inventario_Panol.csv.
    """
    for row in reader:
        panol, _ = Panol.objects.get_or_create(nombre_panol=row['Pañol'])
        ArticuloPanol.objects.update_or_create(
            nombre_articulo=row['Nombre Articulo'],
            panol=panol,
            defaults={
                'descripcion_articulo': row['Descripción'],
                'cantidad': int(row['Cantidad']),
            }
        )

def procesar_inventario_bodega_csv(reader):
    """
    Procesa el archivo Inventario_Bodega.csv.
    """
    for row in reader:
        bodega, _ = Bodega.objects.get_or_create(nombre_bodega=row['Bodega'])
        ArticuloBodega.objects.update_or_create(
            nombre_articulo=row['Nombre Articulo'],
            bodega=bodega,
            defaults={
                'descripcion_articulo': row['Descripción'],
                'cantidad': int(row['Cantidad']),
            }
        )

def procesar_capacitaciones_csv(reader):
    """
    Procesa el archivo Capacitaciones.csv y determina si la capacitación es renovable.
    """
    for row in reader:
        try:
            trabajador = Trabajador.objects.filter(rut=row['RUT']).first()
            if trabajador:
                # Verificar si existe Fecha Fin
                fecha_inicio = row['Fecha Inicio']
                fecha_fin = row['Fecha Fin'] if row['Fecha Fin'] else None
                
                # Determinar si la capacitación es renovable
                es_renovable = True if fecha_fin else False

                # Crear o actualizar la capacitación
                capacitacion, _ = Capacitacion.objects.update_or_create(
                    nombre_capacitacion=row['Capacitacion'],
                    defaults={'es_renovable': es_renovable}
                )

                # Guardar la relación CapacitacionTrabajador
                CapacitacionTrabajador.objects.update_or_create(
                    trabajador=trabajador,
                    capacitacion=capacitacion,
                    defaults={
                        'fecha_inicio': fecha_inicio,
                        'fecha_fin': fecha_fin
                    }
                )
        except Exception as e:
            raise Exception(f"Error al procesar capacitación: {e}")



def procesar_mantenimientos_csv(reader):
    """
    Procesa el archivo Mantenimiento_Maquinaria.csv y registra mantenimientos.
    """
    for row in reader:
        try:
            maquinaria = Maquinaria.objects.get(codigo_maquinaria=row['Código'])
            trabajador = Trabajador.objects.get(nombre_trabajador=row['Realizado Por'])

            MantenimientoMaquinaria.objects.create(
                maquinaria=maquinaria,
                realizado_por=trabajador,
                fecha_mantenimiento=datetime.strptime(row['Fecha Mantenimiento'], "%Y-%m-%d").date(),
                descripcion=row['Descripción']
            )
        except Maquinaria.DoesNotExist:
            raise Exception(f"Error: No existe maquinaria con código {row['Código']}")
        except Trabajador.DoesNotExist:
            raise Exception(f"Error: No existe trabajador {row['Realizado Por']}")
        except Exception as e:
            raise Exception(f"Error en mantenimiento: {e}")

def procesar_trabajos_maquinaria_csv(reader):
    """
    Procesa el archivo Trabajos_Maquinaria.csv.
    """
    for row in reader:
        try:
            maquinaria = Maquinaria.objects.get(codigo_maquinaria=row['Código'])
            trabajador = Trabajador.objects.get(rut=row['RUT'])
            TrabajoMaquinaria.objects.create(
                maquinaria=maquinaria,
                trabajador=trabajador,
                fecha_inicio=timezone.make_aware(datetime.strptime(row['Fecha Inicio'], "%Y-%m-%d %H:%M")),
                fecha_fin=timezone.make_aware(datetime.strptime(row['Fecha Fin'], "%Y-%m-%d %H:%M")),
                descripcion=row['Descripción']
            )
        except Maquinaria.DoesNotExist:
            raise Exception(f"Error: No existe maquinaria con código {row['Código']}")
        except Trabajador.DoesNotExist:
            raise Exception(f"Error: No existe trabajador con RUT {row['RUT']}")
        except Exception as e:
            raise Exception(f"Error en trabajo de maquinaria: {e}")

# =============================================================================
# Inventario: pañol, bodega, traspasos y retiros
# =============================================================================

@login_required
def panol_view(request):
    """
    Inventario del pañol: listado con filtros y alta, edición y eliminación de artículos.
    Las acciones llegan por POST con ?crear, ?editar_id o ?eliminar_id en la URL (ver partials/inventario.html).
    """
    search_query = request.GET.get('q', '')
    ubicacion_id = request.GET.get('ubicacion', '')
    cantidad_filtro = request.GET.get('cantidad_filtro', '')

    articulos = ArticuloPanol.objects.all()

    # Filtro por búsqueda
    if search_query:
        articulos = articulos.filter(
            Q(nombre_articulo__icontains=search_query) |
            Q(descripcion_articulo__icontains=search_query)
        )

    # Filtro por ubicación
    if ubicacion_id:
        articulos = articulos.filter(panol__id=ubicacion_id)

    # Filtro por cantidad
    if cantidad_filtro == 'bajo':
        articulos = articulos.filter(cantidad__lte=10, cantidad__gt=0)
    elif cantidad_filtro == 'agotado':
        articulos = articulos.filter(cantidad=0)

    # Procesar la creación de un artículo
    if request.method == 'POST' and 'crear' in request.POST:
        create_form = ArticuloPanolForm(request.POST)
        if create_form.is_valid():
            create_form.save()
            messages.success(request, "Artículo agregado exitosamente.")
            return redirect('pañol')
        messages.error(request, "No se pudo agregar el artículo: revisa los datos ingresados.")
    else:
        create_form = ArticuloPanolForm()

    # Procesar la edición de un artículo
    if 'editar_id' in request.GET:
        articulo_editar = get_object_or_404(ArticuloPanol, id=request.GET['editar_id'])
        edit_form = ArticuloPanolForm(request.POST or None, instance=articulo_editar)
        
        if request.method == 'POST' and 'editar' in request.POST:
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Artículo editado exitosamente.")
                return redirect('pañol')
            messages.error(request, "No se pudo editar el artículo: revisa los datos ingresados.")
    else:
        edit_form = None

    # Procesar la eliminación de un artículo
    if 'eliminar_id' in request.GET:
        articulo_eliminar = get_object_or_404(ArticuloPanol, id=request.GET['eliminar_id'])
        if request.method == 'POST' and 'eliminar' in request.POST:
            articulo_eliminar.delete()
            messages.success(request, "Artículo eliminado exitosamente.")
            return redirect('pañol')

    advertencias = ArticuloPanol.objects.filter(cantidad__lte=10)
    panoles = Panol.objects.all()

    context = {
        'articulos': articulos,
        'panoles': panoles,
        'search_query': search_query,
        'ubicacion_id': ubicacion_id,
        'cantidad_filtro': cantidad_filtro,
        'advertencias': advertencias,
        'agotados': ArticuloPanol.objects.filter(cantidad=0).count(),
        'create_form': create_form,  # Formulario de creación separado
        'edit_form': edit_form,
    }

    return render(request, 'panol.html', context)

@login_required
def descargar_informe_pañol(request):
    """
    Genera un PDF con los artículos del pañol con stock bajo (≤ 10).
    """
    # Filtrar artículos con cantidad baja o agotada
    articulos_bajos = ArticuloPanol.objects.filter(cantidad__lte=10)

    # Configuración del PDF en orientación horizontal
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []

    # Encabezado de la tabla
    data = [
        ["Nombre", "Descripción", "Cantidad", "Ubicación"]
    ]

    # Estilo de la tabla con mayor espacio entre celdas y mejor apariencia
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])

    # Agregar datos de cada artículo
    for articulo in articulos_bajos:
        data.append([
            articulo.nombre_articulo,
            articulo.descripcion_articulo,
            articulo.cantidad,
            articulo.panol.nombre_panol
        ])

    # Crear la tabla y definir el ancho de columnas
    table = Table(data, colWidths=[1*inch, 2*inch, 3*inch, 1*inch, 1.5*inch])
    table.setStyle(table_style)
    elements.append(table)

    # Construcción del PDF
    pdf.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="informe_articulos_bajos.pdf"'
    return response


@login_required
def bodega_view(request):
    """
    Inventario de bodega: misma lógica que panol_view, pero sobre ArticuloBodega.
    """
    search_query = request.GET.get('q', '')
    ubicacion_id = request.GET.get('ubicacion', '')
    cantidad_filtro = request.GET.get('cantidad_filtro', '')

    # Obtener todos los artículos en bodega
    articulos = ArticuloBodega.objects.all()

    # Filtrar por búsqueda
    if search_query:
        articulos = articulos.filter(
            Q(nombre_articulo__icontains=search_query) |
            Q(descripcion_articulo__icontains=search_query)
        )

    # Filtrar por ubicación
    if ubicacion_id:
        articulos = articulos.filter(bodega__id=ubicacion_id)

    # Filtrar por cantidad
    if cantidad_filtro == 'bajo':
        articulos = articulos.filter(cantidad__lte=10, cantidad__gt=0)
    elif cantidad_filtro == 'agotado':
        articulos = articulos.filter(cantidad=0)

    # Procesar la creación de un artículo
    if request.method == 'POST' and 'crear' in request.POST:
        create_form = ArticuloBodegaForm(request.POST)
        if create_form.is_valid():
            create_form.save()
            messages.success(request, "Artículo agregado exitosamente en la bodega.")
            return redirect('bodega')
        messages.error(request, "No se pudo agregar el artículo: revisa los datos ingresados.")
    else:
        create_form = ArticuloBodegaForm()

    # Procesar la edición de un artículo
    if 'editar_id' in request.GET:
        articulo_editar = get_object_or_404(ArticuloBodega, id=request.GET['editar_id'])
        edit_form = ArticuloBodegaForm(request.POST or None, instance=articulo_editar)
        
        if request.method == 'POST' and 'editar' in request.POST:
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, "Artículo editado exitosamente.")
                return redirect('bodega')
            messages.error(request, "No se pudo editar el artículo: revisa los datos ingresados.")
    else:
        edit_form = None

    # Procesar la eliminación de un artículo
    if 'eliminar_id' in request.GET:
        articulo_eliminar = get_object_or_404(ArticuloBodega, id=request.GET['eliminar_id'])
        if request.method == 'POST' and 'eliminar' in request.POST:
            articulo_eliminar.delete()
            messages.success(request, "Artículo eliminado exitosamente.")
            return redirect('bodega')

    # Obtener advertencias para artículos con baja cantidad
    advertencias = ArticuloBodega.objects.filter(cantidad__lte=10)
    bodegas = Bodega.objects.all()

    context = {
        'articulos': articulos,
        'bodegas': bodegas,
        'search_query': search_query,
        'ubicacion_id': ubicacion_id,
        'cantidad_filtro': cantidad_filtro,
        'advertencias': advertencias,
        'agotados': ArticuloBodega.objects.filter(cantidad=0).count(),
        'create_form': create_form,  # Formulario de creación
        'edit_form': edit_form,      # Formulario de edición, si aplica
    }

    return render(request, 'bodega.html', context)


@login_required
def descargar_informe_bodega(request):
    """
    Genera un PDF con los artículos de bodega con stock bajo (≤ 10).
    """
    # Filter articles with low or zero quantity in "bodega"
    articulos_bajos = ArticuloBodega.objects.filter(cantidad__lte=10)

    # Configure the PDF layout in landscape orientation
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []

    # Table header
    data = [
        ["Nombre", "Descripción", "Cantidad", "Ubicación"]
    ]

    # Define the table style with more padding and better appearance
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])

    # Add data for each article
    for articulo in articulos_bajos:
        data.append([
            articulo.nombre_articulo,
            articulo.descripcion_articulo,
            articulo.cantidad,
            articulo.bodega.nombre_bodega
        ])

    # Create the table and define column widths
    table = Table(data, colWidths=[2*inch, 3*inch, 1*inch, 2*inch])
    table.setStyle(table_style)
    elements.append(table)

    # Build the PDF
    pdf.build(elements)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="informe_bodega_bajo_stock.pdf"'
    return response


@login_required
def obtener_articulos_por_bodega(request, bodega_id):
    """
    Devuelve los artículos disponibles en la bodega seleccionada.
    """
    articulos = ArticuloBodega.objects.filter(
        bodega_id=bodega_id,  # Coincide con la bodega seleccionada
        cantidad__gt=0        # Cantidad mayor que 0
    ).values(
        'id', 'nombre_articulo', 'cantidad'
    )
    return JsonResponse(list(articulos), safe=False)

@login_required
def mover_articulo_view(request):
    """
    Traspaso de artículos de una bodega a un pañol, con historial de movimientos.
    """
    # Cargar las bodegas y pañoles
    bodegas = Bodega.objects.all()
    panoles = Panol.objects.all()

    # Si es POST, procesar el movimiento
    if request.method == 'POST':
        articulo_id = request.POST.get('articulo')
        cantidad = int(request.POST.get('cantidad'))
        origen_id = request.POST.get('origen')
        destino_id = request.POST.get('destino')
        motivo = request.POST.get('motivo', '')

        # Validar el artículo y las cantidades
        articulo = get_object_or_404(ArticuloBodega, id=articulo_id, bodega_id=origen_id)
        destino = get_object_or_404(Panol, id=destino_id)

        if cantidad < 1 or cantidad > articulo.cantidad:
            messages.error(request, "La cantidad debe ser mayor a 0 y no puede exceder el stock disponible.")
            return redirect('mover_articulo')

        # Descuenta de bodega, suma al pañol y registra el movimiento (models.MovimientoArticulo)
        MovimientoArticulo.mover_articulo(articulo, destino, cantidad, motivo)
        messages.success(request, f"Se movieron {cantidad} × {articulo.nombre_articulo} a {destino.nombre_panol}.")
        return redirect('mover_articulo')

    # Historial de movimientos
    historial = MovimientoArticulo.objects.all().order_by('-fecha_movimiento')

    context = {
        'bodegas': bodegas,
        'panoles': panoles,
        'historial': historial,
    }
    return render(request, 'mover_articulo.html', context)

@login_required
def retiro_articulo_view(request):
    """
    Préstamo de artículos del pañol a trabajadores (descuenta stock) e historial de retiros.
    """
    # Historial de retiros ordenados por fecha más reciente
    retiros = RetiroArticulo.objects.all().order_by('-fecha_retiro', '-id')

    # Procesar formulario de retiro
    if request.method == 'POST':
        form = RetiroArticuloForm(request.POST)
        if form.is_valid():
            trabajador = form.cleaned_data['trabajador']
            articulo = form.cleaned_data['articulo']
            cantidad = form.cleaned_data['cantidad']

            # Validar que la cantidad solicitada no exceda el inventario
            if articulo.cantidad >= cantidad:
                articulo.cantidad -= cantidad  # Descontar la cantidad retirada
                articulo.save()

                # Crear el registro de retiro
                retiro = RetiroArticulo.objects.create(
                    trabajador=trabajador,
                    articulo=articulo,
                    cantidad=cantidad
                )
                retiro.save()
                messages.success(request, "El retiro se registró correctamente.")
                return redirect('retiro_articulo')
            else:
                messages.error(request, "La cantidad solicitada excede el inventario disponible.")
        else:
            messages.error(request, "Por favor, corrija los errores en el formulario.")
    else:
        form = RetiroArticuloForm()

    context = {
        'form': form,
        'retiros': retiros,
    }
    return render(request, 'retiro_articulo.html', context)

@login_required
def devolver_articulo(request, retiro_id):
    """
    Registra la devolución de un retiro y repone el stock del pañol. Solo acepta POST.
    """
    if request.method != 'POST':
        return redirect('retiro_articulo')

    retiro = get_object_or_404(RetiroArticulo, id=retiro_id)

    # Verificar si ya fue devuelto
    if not retiro.es_devuelto:  # Solo si no se ha devuelto aún
        retiro.fecha_devuelta = timezone.now()  # Asignar la fecha actual como devolución
        retiro.es_devuelto = True  # Marcar el estado como devuelto

        # Devolver la cantidad al inventario del artículo
        retiro.articulo.cantidad += retiro.cantidad  # Incrementar el stock del artículo
        retiro.articulo.save()

        retiro.save()  # Guardar los cambios en el registro existente

        messages.success(request, "El artículo ha sido devuelto correctamente.")
    else:
        messages.warning(request, "Este artículo ya fue devuelto anteriormente.")

    return redirect('retiro_articulo')  # Redirigir a la página de historial

def normalizar_rut(rut):
    """
    Deja el RUT en el formato que usa el sistema: sin puntos, con guion y K mayúscula (12345678-K).
    """
    limpio = rut.replace(".", "").replace("-", "").strip().upper()
    return f"{limpio[:-1]}-{limpio[-1]}"




# =============================================================================
# Trabajadores y certificaciones
# =============================================================================

@login_required
def trabajadores_view(request):
    """
    Listado de trabajadores activos con búsqueda y filtros por área, turno y vencimiento de certificaciones.
    """
    trabajadores = Trabajador.objects.filter(activo=True)

    # Filtrar por búsqueda general
    search_query = request.GET.get('search', '')
    if search_query:
        trabajadores = trabajadores.filter(
            Q(nombre_trabajador__icontains=search_query) |
            Q(rut__icontains=search_query) |
            Q(area__nombre_area__icontains=search_query) |
            Q(cargo__nombre_cargo__icontains=search_query)
        )

    # Filtrar por área
    area_id = request.GET.get('area', '')
    if area_id:
        trabajadores = trabajadores.filter(area_id=area_id)

    # Filtrar por turno
    turno = request.GET.get('turno', '')
    if turno:
        trabajadores = trabajadores.filter(turno__tipo_turno=turno)

    # Filtrar por certificaciones próximas a expirar o expiradas
    certificacion = request.GET.get('certificacion', '')
    if certificacion == "expira_90":
        fecha_limite = now() + timedelta(days=90)
        trabajadores = trabajadores.filter(
            capacitaciontrabajador__fecha_fin__lte=fecha_limite,
            capacitaciontrabajador__fecha_fin__gte=now()
        )
    elif certificacion == "expira_30":
        fecha_limite = now() + timedelta(days=30)
        trabajadores = trabajadores.filter(
            capacitaciontrabajador__fecha_fin__lte=fecha_limite,
            capacitaciontrabajador__fecha_fin__gte=now()
        )
    elif certificacion == "expirada":
        trabajadores = trabajadores.filter(
            capacitaciontrabajador__fecha_fin__lt=now()
        )

    # Advertencia de certificaciones próximas a expirar
    advertencia = CapacitacionTrabajador.objects.filter(
        trabajador__activo=True,
        fecha_fin__lte=now() + timedelta(days=90),  # Próximas a expirar en 90 días
        fecha_fin__gte=now()
    ).exists()

    # Preparar datos para el template, incluyendo certificaciones
    trabajadores_data = []
    for trabajador in trabajadores:
        horas_trabajadas = trabajador.registrohoras_set.aggregate(total=Sum('horas_trabajadas'))['total'] or 0
        horas_esperadas = trabajador.registrohoras_set.aggregate(total=Sum('horas_esperadas'))['total'] or 0
        certificaciones = CapacitacionTrabajador.objects.filter(trabajador=trabajador).select_related('capacitacion')

        # Resumen para la columna "Certificaciones" de la tabla
        hoy = now().date()
        vencidas = sum(1 for c in certificaciones if c.fecha_fin and c.fecha_fin < hoy)
        por_vencer = sum(1 for c in certificaciones if c.fecha_fin and hoy <= c.fecha_fin <= hoy + timedelta(days=90))

        trabajadores_data.append({
            'trabajador': trabajador,
            'horas_trabajadas': horas_trabajadas,
            'horas_esperadas': horas_esperadas,
            'certificaciones': certificaciones,
            'vencidas': vencidas,
            'por_vencer': por_vencer,
        })

    context = {
        'trabajadores_data': trabajadores_data,
        'areas': Area.objects.all(),
        'advertencia': advertencia,
    }
    return render(request, 'trabajadores.html', context)


@login_required
def add_trabajador_view(request):
    """
    Formulario para crear un trabajador, su registro de horas y sus certificaciones iniciales.
    """
    if request.method == "POST":
        # Normalizar el RUT
        rut = normalizar_rut(request.POST.get('rut'))
        
        # Los demás datos
        nombre = request.POST.get('nombre')
        area_id = request.POST.get('area')
        cargo_id = request.POST.get('cargo')
        jornada_id = request.POST.get('jornada')
        turno_id = request.POST.get('turno')
        horario_id = request.POST.get('horario')
        horas_esperadas = int(request.POST.get('horas_esperadas', 40))

        # Verificar si el trabajador ya existe
        if Trabajador.objects.filter(rut=rut).exists():
            messages.error(request, f"Ya existe un trabajador con el RUT {rut}.")
            return redirect('add_trabajador')

        # Crear el trabajador
        trabajador = Trabajador.objects.create(
            rut=rut,
            nombre_trabajador=nombre,
            area=get_object_or_404(Area, id=area_id),
            cargo=get_object_or_404(Cargo, id=cargo_id),
            jornada=get_object_or_404(Jornada, id=jornada_id),
            turno=get_object_or_404(Turno, id=turno_id),
            horario=get_object_or_404(Horario, id=horario_id),
        )

        # Registrar horas trabajadas
        RegistroHoras.objects.create(
            trabajador=trabajador,
            area=trabajador.area,
            horas_trabajadas=0,
            horas_esperadas=horas_esperadas,
            fecha_registro=timezone.now()
        )

        guardar_certificaciones_nuevas(trabajador, request.POST)

        messages.success(request, f"El trabajador {nombre} fue agregado exitosamente.")
        return redirect('gestion_trabajadores')

    # Obtener datos para los dropdowns
    context = {
        'areas': Area.objects.all(),
        'cargos': Cargo.objects.all(),
        'jornadas': Jornada.objects.all(),
        'turnos': Turno.objects.all(),
        'horarios': Horario.objects.all(),
        'capacitaciones_disponibles': Capacitacion.objects.all(),
    }
    return render(request, 'add_trabajador.html', context)


def guardar_certificaciones_nuevas(trabajador, datos):
    """
    Crea las certificaciones agregadas en el formulario (campos certificacion_nueva_N,
    fecha_inicio_nueva_N y fecha_fin_nueva_N). La fecha de fin solo se guarda si la
    certificación es renovable.
    """
    for clave, valor in datos.items():
        if not clave.startswith('certificacion_nueva_'):
            continue
        numero = clave.rsplit('_', 1)[-1]
        capacitacion = get_object_or_404(Capacitacion, id=valor)
        fecha_fin = datos.get(f'fecha_fin_nueva_{numero}') if capacitacion.es_renovable else None
        CapacitacionTrabajador.objects.create(
            trabajador=trabajador,
            capacitacion=capacitacion,
            fecha_inicio=datos.get(f'fecha_inicio_nueva_{numero}'),
            fecha_fin=fecha_fin or None,
        )

@login_required
def editar_trabajador(request, rut):
    """
    Edita datos, horas y certificaciones de un trabajador.
    """
    trabajador = get_object_or_404(Trabajador, rut=rut)

    if request.method == 'POST':
        # Actualizar información básica del trabajador
        trabajador.nombre_trabajador = request.POST.get('nombre')
        area_id = request.POST.get('area')
        cargo_id = request.POST.get('cargo')
        jornada_id = request.POST.get('jornada')
        horario_id = request.POST.get('horario')
        turno_id = request.POST.get('turno')

        if area_id:
            trabajador.area = get_object_or_404(Area, id=area_id)
        if cargo_id:
            trabajador.cargo = get_object_or_404(Cargo, id=cargo_id)
        if jornada_id:
            trabajador.jornada = get_object_or_404(Jornada, id=jornada_id)
        if horario_id:
            trabajador.horario = get_object_or_404(Horario, id=horario_id)
        if turno_id:
            trabajador.turno = get_object_or_404(Turno, id=turno_id)

        trabajador.save()

        # Actualizar horas esperadas y trabajadas
        registro_horas = RegistroHoras.objects.filter(trabajador=trabajador).first()
        if registro_horas:
            registro_horas.horas_esperadas = request.POST.get('horas_esperadas', registro_horas.horas_esperadas)
            registro_horas.horas_trabajadas = request.POST.get('horas_trabajadas', registro_horas.horas_trabajadas)
            registro_horas.save()
        else:
            RegistroHoras.objects.create(
                trabajador=trabajador,
                area=trabajador.area,
                horas_esperadas=request.POST.get('horas_esperadas', 40),
                horas_trabajadas=request.POST.get('horas_trabajadas', 0),
                fecha_registro=timezone.now()
            )

        # Manejo de certificaciones
        certificaciones_a_eliminar = request.POST.getlist('certificaciones_eliminar')
        for cert_id in certificaciones_a_eliminar:
            certificacion = get_object_or_404(CapacitacionTrabajador, id=cert_id)
            certificacion.delete()

        for cert in trabajador.capacitaciontrabajador_set.all():
            fecha_inicio = request.POST.get(f'fecha_inicio_{cert.id}')
            fecha_fin = request.POST.get(f'fecha_fin_{cert.id}') if cert.capacitacion.es_renovable else None
            if fecha_inicio:
                cert.fecha_inicio = fecha_inicio
            if fecha_fin:
                cert.fecha_fin = fecha_fin
            cert.save()

        guardar_certificaciones_nuevas(trabajador, request.POST)

        messages.success(request, 'El trabajador ha sido actualizado correctamente.')
        return redirect('gestion_trabajadores')

    # Obtener datos para mostrar
    registro_horas = RegistroHoras.objects.filter(trabajador=trabajador).first()
    horas_esperadas = registro_horas.horas_esperadas if registro_horas else 40
    horas_trabajadas = registro_horas.horas_trabajadas if registro_horas else 0

    certificaciones_disponibles = Capacitacion.objects.all()

    context = {
        'trabajador': trabajador,
        'areas': Area.objects.all(),
        'cargos': Cargo.objects.all(),
        'jornadas': Jornada.objects.all(),
        'horarios': Horario.objects.all(),
        'turnos': Turno.objects.all(),
        'certificaciones': trabajador.capacitaciontrabajador_set.all(),
        'capacitaciones_disponibles': certificaciones_disponibles,
        'horas_esperadas': horas_esperadas,
        'horas_trabajadas': horas_trabajadas,
    }
    return render(request, 'editar_trabajador.html', context)


@login_required
def eliminar_certificacion(request, cert_id):
    """
    Elimina la certificación asignada a un trabajador. Se llama por fetch desde editar_trabajador.html.
    """
    try:
        certificacion = get_object_or_404(CapacitacionTrabajador, id=cert_id)
        certificacion.delete()
        return JsonResponse({'success': True, 'message': 'Certificación eliminada correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error al eliminar certificación: {str(e)}'})


@login_required
def eliminar_trabajador(request):
    """
    Da de baja a un trabajador (activo=False) sin borrar su historial.
    Recibe {"rut": "..."} por POST/JSON desde trabajadores.html.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido.'}, status=405)

    rut = json.loads(request.body).get('rut', '').strip()
    try:
        trabajador = Trabajador.objects.get(rut=rut)
    except Trabajador.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Trabajador con RUT {rut} no encontrado.'})

    trabajador.activo = False
    trabajador.save()
    return JsonResponse({'success': True, 'message': 'Trabajador dado de baja correctamente.'})


@login_required
def agregar_capacitacion(request):
    """
    Crea un nuevo tipo de certificación. Recibe {"nombre": str, "es_renovable": bool}
    por POST/JSON desde el modal "Nuevo tipo de certificación" de trabajadores.html.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Método no permitido.'}, status=405)

    datos = json.loads(request.body)
    nombre = datos.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'success': False, 'message': 'El nombre es obligatorio.'})
    if Capacitacion.objects.filter(nombre_capacitacion__iexact=nombre).exists():
        return JsonResponse({'success': False, 'message': f'Ya existe la certificación "{nombre}".'})

    Capacitacion.objects.create(nombre_capacitacion=nombre, es_renovable=bool(datos.get('es_renovable')))
    messages.success(request, f'Certificación "{nombre}" creada. Ya puedes asignarla a los trabajadores.')
    return JsonResponse({'success': True})

@login_required
def descargar_informe_trabajadores(request):
    """
    Genera un PDF con las certificaciones que vencen en los próximos 30 días.
    """
    fecha_limite = now() + timedelta(days=30)
    trabajadores = Trabajador.objects.filter(
        capacitaciontrabajador__fecha_fin__lte=fecha_limite
    ).distinct()

    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []

    # Encabezado
    data = [
        ["RUT", "Nombre", "Área", "Puesto", "Certificación", "Fecha de Expiración"]
    ]

    # Detalles
    for trabajador in trabajadores:
        certificaciones = CapacitacionTrabajador.objects.filter(
            trabajador=trabajador, fecha_fin__lte=fecha_limite
        )
        for cert in certificaciones:
            data.append([
                trabajador.rut,
                trabajador.nombre_trabajador,
                trabajador.area.nombre_area,
                trabajador.cargo.nombre_cargo,
                cert.capacitacion.nombre_capacitacion,
                cert.fecha_fin.strftime('%d-%m-%Y'),
            ])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(table)
    pdf.build(elements)
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename="informe_trabajadores.pdf")


# =============================================================================
# Maquinaria: estado, mantenimientos y trabajos
# =============================================================================

# Estados válidos de un equipo (son los textos que se guardan en Maquinaria.estado)
ESTADOS_MAQUINARIA = ('Activo', 'En Mantenimiento', 'Inactivo')


@login_required
def maquinaria_view(request):
    """
    Listado de equipos con búsqueda y filtros por estado y área.
    """
    # Lista inicial de maquinarias
    maquinarias = Maquinaria.objects.all()

    # Filtrar maquinarias activas y trabajadores activos para los dropdowns
    maquinarias_activas = Maquinaria.objects.filter(estado="Activo")
    trabajadores_activos = Trabajador.objects.filter(activo=True)

    # Filtros de búsqueda
    search_query = request.GET.get('search', '')
    if search_query:
        maquinarias = maquinarias.filter(
            Q(nombre_maquinaria__icontains=search_query) |
            Q(area__nombre_area__icontains=search_query) |
            Q(estado__icontains=search_query)
        )

    # Filtrar por estado
    estado = request.GET.get('estado', '')
    if estado:
        maquinarias = maquinarias.filter(estado=estado)

    # Filtrar por área
    area_id = request.GET.get('area', '')
    if area_id:
        maquinarias = maquinarias.filter(area_id=area_id)

    # Contexto para el template
    context = {
        'maquinarias': maquinarias,
        'maquinarias_activas': maquinarias_activas,
        'trabajadores_activos': trabajadores_activos,
        'areas': Area.objects.all(),
        'estados': dict(Maquinaria.ESTADOS),
        'selected_estado': estado,
        'selected_area': area_id,
        'search_query': search_query,
    }

    return render(request, 'maquinaria.html', context)




@login_required
def edit_maquinaria(request, maquinaria_id):
    """
    Cambia el estado de un equipo (Activo, En Mantenimiento o Inactivo) desde el modal de maquinaria.html.
    """
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)

    if request.method == 'POST':
        estado = request.POST.get('estado')
        if estado not in ESTADOS_MAQUINARIA:
            messages.error(request, "Estado no válido.")
            return redirect('maquinaria')

        maquinaria.estado = estado
        maquinaria.save()
        messages.success(request, f"{maquinaria.nombre_maquinaria} quedó en estado «{estado}».")
        return redirect('maquinaria')

    return JsonResponse({'error': 'Método no permitido.'}, status=405)


    
    
@login_required
def add_mantenimiento(request):
    """
    Registra un mantenimiento con fecha de hoy. Si el equipo no queda operativo, pasa a "En Mantenimiento".
    """
    if request.method == "POST":
        maquinaria_id = request.POST.get('maquinaria')
        trabajador_id = request.POST.get('trabajador')
        descripcion = request.POST.get('descripcion')  # Capturar la descripción
        estado_activo = request.POST.get('estado_activo') == "on"

        try:
            maquinaria = Maquinaria.objects.get(id=maquinaria_id)
            trabajador = Trabajador.objects.get(rut=trabajador_id)

            # Guardar mantenimiento con descripción
            MantenimientoMaquinaria.objects.create(
                maquinaria=maquinaria,
                realizado_por=trabajador,
                fecha_mantenimiento=timezone.now().date(),
                descripcion=descripcion  # Guardar la descripción
            )

            # Actualizar estado de la maquinaria
            if not estado_activo:
                maquinaria.estado = "En Mantenimiento"
                maquinaria.save()

            messages.success(request, "Mantenimiento registrado correctamente.")
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect('maquinaria')

@login_required
def add_trabajo_maquinaria(request):
    """
    Registra un trabajo con un equipo. El trabajo termina ahora y empieza `horas_trabajadas` antes.
    """
    if request.method == "POST":
        maquinaria_id = request.POST.get("maquinaria")
        trabajador_rut = request.POST.get("trabajador")
        horas_trabajadas = request.POST.get("horas_trabajadas")
        descripcion = request.POST.get("descripcion")

        try:
            # Validar campos
            if not horas_trabajadas or not descripcion:
                messages.error(request, "Todos los campos son obligatorios.")
                return redirect('maquinaria')

            if int(horas_trabajadas) > 24 or int(horas_trabajadas) < 1:
                messages.error(request, "Las horas trabajadas deben estar entre 1 y 24.")
                return redirect('maquinaria')

            # Obtener instancias
            maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
            trabajador = get_object_or_404(Trabajador, rut=trabajador_rut)

            # Guardar el trabajo (termina ahora; las horas se calculan desde inicio y fin)
            fecha_fin = timezone.now()
            TrabajoMaquinaria.objects.create(
                maquinaria=maquinaria,
                trabajador=trabajador,
                fecha_inicio=fecha_fin - timedelta(hours=int(horas_trabajadas)),
                fecha_fin=fecha_fin,
                descripcion=descripcion
            )

            messages.success(request, "Trabajo agregado exitosamente.")
            return redirect('maquinaria')

        except Exception as e:
            messages.error(request, f"Error al guardar el trabajo: {e}")
            return redirect('maquinaria')

    else:
        return JsonResponse({"error": "Método no permitido"}, status=405)

@login_required
def desactivar_maquinaria(request, maquinaria_id):
    """
    Cambia el estado de una maquinaria a 'Inactivo' en lugar de eliminarla.
    """
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    if request.method == "POST":
        maquinaria.estado = "Inactivo"  # Actualiza el estado
        maquinaria.save()  # Guarda los cambios en la base de datos
        messages.success(request, f"La maquinaria '{maquinaria.nombre_maquinaria}' ha sido desactivada.")
        return redirect('maquinaria')  # Redirige a la vista de maquinarias
    return redirect('maquinaria')





@login_required
def ver_mantenimientos(request, maquinaria_id):
    """
    Historial de mantenimientos de un equipo, con búsqueda.
    """
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    search_query = request.GET.get('search', '')

    # Filtrar mantenimientos por búsqueda
    mantenimientos = MantenimientoMaquinaria.objects.filter(maquinaria=maquinaria).order_by('-fecha_mantenimiento')

    if search_query:
        mantenimientos = mantenimientos.filter(
            Q(realizado_por__nombre_trabajador__icontains=search_query) |  # Buscar por nombre del trabajador
            Q(realizado_por__rut__icontains=search_query) |               # Buscar por RUT del trabajador
            Q(descripcion__icontains=search_query) |                      # Buscar en descripción
            Q(fecha_mantenimiento__icontains=search_query)                # Buscar en fecha
        )

    return render(request, 'ver_mantenimientos.html', {'mantenimientos': mantenimientos, 'maquinaria': maquinaria, 'search_query': search_query})


@login_required
def ver_trabajos(request, maquinaria_id):
    """
    Historial de trabajos realizados con un equipo, con búsqueda.
    """
    maquinaria = get_object_or_404(Maquinaria, id=maquinaria_id)
    search_query = request.GET.get('search', '')

    # Filtrar trabajos por búsqueda
    trabajos = TrabajoMaquinaria.objects.filter(maquinaria=maquinaria).order_by('-fecha_inicio')

    if search_query:
        trabajos = trabajos.filter(
            Q(trabajador__nombre_trabajador__icontains=search_query) |  # Buscar por nombre del trabajador
            Q(trabajador__rut__icontains=search_query) |               # Buscar por RUT del trabajador
            Q(descripcion__icontains=search_query) |                   # Buscar en descripción
            Q(fecha_inicio__icontains=search_query)                    # Buscar en fecha
        )

    return render(request, 'ver_trabajos.html', {'trabajos': trabajos, 'maquinaria': maquinaria, 'search_query': search_query})