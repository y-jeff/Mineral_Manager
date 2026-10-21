"""
Comando `python manage.py cargar_demo`.

Deja la aplicación lista para probar: crea la cuenta de demostración y carga una faena
minera de ejemplo (la misma que trae el Excel de static/ejemplos), además de algunos
retiros y traspasos para que todas las pantallas tengan información.
"""
from io import BytesIO

from django.core.management.base import BaseCommand
from django.db import transaction

from MineralApp import demo
from MineralApp.models import (
    Area, ArticuloBodega, ArticuloPanol, Bodega, Capacitacion, CapacitacionTrabajador, Cargo,
    CustomUser, Horario, Jornada, MantenimientoMaquinaria, Maquinaria, MovimientoArticulo,
    Panol, RegistroHoras, RetiroArticulo, Trabajador, TrabajoMaquinaria, Turno,
)
from MineralApp.views import procesar_archivo_excel

DEMO_USUARIO = 'demo'
DEMO_CLAVE = 'demo1234'

# Orden de borrado para --reset: primero las tablas que dependen de otras
MODELOS_A_BORRAR = [
    RetiroArticulo, MovimientoArticulo, TrabajoMaquinaria, MantenimientoMaquinaria,
    RegistroHoras, CapacitacionTrabajador, ArticuloPanol, ArticuloBodega, Maquinaria,
    Trabajador, Capacitacion, Panol, Bodega, Area, Cargo, Jornada, Turno, Horario,
]


class Command(BaseCommand):
    help = 'Crea la cuenta demo (demo / demo1234) y carga datos de ejemplo.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='Borra todos los datos de la faena antes de cargar la demo (no borra usuarios).')
        parser.add_argument('--excel', action='store_true',
                            help='Regenera static/ejemplos/MineralManager_Datos_Prueba.xlsx con las fechas de hoy.')

    def handle(self, *args, **opciones):
        if opciones['excel']:
            demo.construir_libro().save(demo.EXCEL_EJEMPLO)
            self.stdout.write(self.style.SUCCESS(f'Excel generado en {demo.EXCEL_EJEMPLO}'))

        if opciones['reset']:
            self.borrar_datos()

        if Trabajador.objects.exists():
            self.stdout.write(self.style.WARNING(
                'La base ya tiene datos: no se cargó la demo. Usa --reset para reemplazarlos.'))
        else:
            self.cargar_datos()

        self.crear_usuario_demo()
        self.stdout.write(self.style.SUCCESS(
            f'\nListo. Ejecuta "python manage.py runserver" y entra con {DEMO_USUARIO} / {DEMO_CLAVE}'))

    @transaction.atomic
    def borrar_datos(self):
        for modelo in MODELOS_A_BORRAR:
            modelo.objects.all().delete()
        self.stdout.write('Datos anteriores eliminados.')

    @transaction.atomic
    def cargar_datos(self):
        # Se usa el mismo proceso que la pantalla "Carga de datos", así la demo también lo prueba
        archivo = BytesIO()
        demo.construir_libro().save(archivo)
        archivo.seek(0)
        procesar_archivo_excel('demo.xlsx', archivo)

        # Retiros del pañol: uno pendiente y uno ya devuelto
        for rut, articulo, cantidad, devuelto in [
            ('12345678-9', 'Taladro Inalámbrico', 2, False),
            ('17654321-K', 'Linterna Minera', 3, True),
            ('13678901-4', 'Llave de Torque', 1, False),
        ]:
            item = ArticuloPanol.objects.get(nombre_articulo=articulo)
            item.cantidad -= cantidad
            item.save()
            RetiroArticulo.objects.create(trabajador=Trabajador.objects.get(rut=rut), articulo=item,
                                          cantidad=cantidad, es_devuelto=devuelto)

        # Traspasos de bodega a pañol
        panol_mina = Panol.objects.get(nombre_panol='Pañol Mina')
        for articulo, cantidad, motivo in [
            ('Guantes de Cuero', 10, 'Reposición semanal'),
            ('Casco de Seguridad', 5, 'Ingreso de personal nuevo'),
        ]:
            MovimientoArticulo.mover_articulo(ArticuloBodega.objects.get(nombre_articulo=articulo),
                                              panol_mina, cantidad, motivo)

        self.stdout.write(f'Datos de ejemplo cargados: {Trabajador.objects.count()} trabajadores, '
                          f'{Maquinaria.objects.count()} equipos, '
                          f'{ArticuloBodega.objects.count() + ArticuloPanol.objects.count()} artículos.')

    def crear_usuario_demo(self):
        # Usuario normal (no superusuario): entra directo a la aplicación
        usuario, creado = CustomUser.objects.get_or_create(
            username=DEMO_USUARIO, defaults={'email': 'demo@mineralmanager.cl'})
        usuario.set_password(DEMO_CLAVE)
        usuario.is_active = True
        usuario.save()
        self.stdout.write(f'Cuenta demo {"creada" if creado else "actualizada"}: {DEMO_USUARIO} / {DEMO_CLAVE}')
