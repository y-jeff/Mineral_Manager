"""
Modelos de datos de Mineral Manager.
"""
from django.db import models
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError

class CustomUserManager(BaseUserManager):
    """Crea usuarios y superusuarios del modelo CustomUser (login por nombre de usuario)."""

    def create_user(self, username, email, password=None):
        if not email:
            raise ValueError("El usuario debe tener un correo electrónico.")
        if not username:
            raise ValueError("El usuario debe tener un nombre de usuario.")

        user = self.model(
            email=self.normalize_email(email),
            username=username,
            date_joined=timezone.now()
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None):
        user = self.create_user(
            email=email,
            username=username,
            password=password,
        )
        user.is_admin = True
        user.is_staff = True
        user.is_superuser = True  # Aquí definimos directamente el campo
        user.save(using=self._db)
        return user

class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Usuario del sistema. Inicia sesión con `username`; el correo se usa para recuperar la contraseña."""

    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=60, unique=True)
    email_confirmed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)  # Campo requerido por Django Admin
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    def __str__(self):
        return self.username
    
class Area(models.Model):
    """Área de la faena (Extracción, Planta, Mantenimiento...). Agrupa trabajadores y maquinaria."""

    nombre_area = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre_area

class Cargo(models.Model):
    """Cargo o puesto de un trabajador."""

    nombre_cargo = models.CharField(max_length=256, unique=True)

    def __str__(self):
        return self.nombre_cargo

class Jornada(models.Model):
    """Tipo de jornada: Diurna o Nocturna."""

    tipo_jornada = models.CharField(max_length=10, unique=True)

    def __str__(self):
        return self.tipo_jornada

class Turno(models.Model):
    """Turno de trabajo: A o B."""

    tipo_turno = models.CharField(max_length=1, choices=[('A', 'A'), ('B', 'B')])

    def __str__(self):
        return f"Turno {self.tipo_turno}"

class Horario(models.Model):
    """Ciclo de trabajo/descanso, por ejemplo 7x7, 4x3 o 5x2."""

    ciclo = models.CharField(max_length=10)
    def __str__(self):
        return f"Ciclo {self.ciclo}"

class Trabajador(models.Model):
    """Trabajador de la faena, identificado por su RUT. Las bajas se hacen con `activo=False`
    para conservar su historial."""

    rut = models.CharField(max_length=100, primary_key=True)
    nombre_trabajador = models.CharField(max_length=256)
    area = models.ForeignKey(Area, on_delete=models.RESTRICT)
    cargo = models.ForeignKey(Cargo, on_delete=models.RESTRICT)
    jornada = models.ForeignKey(Jornada, on_delete=models.RESTRICT)
    turno = models.ForeignKey(Turno, on_delete=models.RESTRICT)
    horario = models.ForeignKey(Horario, on_delete=models.RESTRICT)
    activo = models.BooleanField(default=True) 

    def __str__(self):
        return f"{self.nombre_trabajador} ({self.rut})"
    
class Capacitacion(models.Model):
    """Tipo de certificación. Si es renovable, cada asignación tiene fecha de vencimiento."""

    nombre_capacitacion = models.CharField(max_length=256)
    es_renovable = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre_capacitacion

    

class CapacitacionTrabajador(models.Model):
    """Certificación asignada a un trabajador, con su fecha de inicio y, si es renovable, de vencimiento."""

    trabajador = models.ForeignKey(Trabajador, on_delete=models.RESTRICT)
    capacitacion = models.ForeignKey(Capacitacion, on_delete=models.RESTRICT)
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(null=True, blank=True)  # Opcional

    def clean(self):
        # Asegúrate de que `fecha_fin` sea nula si no es renovable
        if not self.capacitacion.es_renovable and self.fecha_fin:
            raise ValidationError("Las capacitaciones no renovables no deben tener fecha de finalización.")

    def save(self, *args, **kwargs):
        # Llama a la validación antes de guardar
        self.full_clean()
        super().save(*args, **kwargs)

class Panol(models.Model):
    """Pañol: lugar desde donde se prestan herramientas a los trabajadores."""

    nombre_panol = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre_panol

class Bodega(models.Model):
    """Bodega de insumos y repuestos. Abastece a los pañoles."""

    nombre_bodega = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre_bodega
class Producto(models.Model):
    """Modelo heredado de una versión anterior; se mantiene por compatibilidad con las migraciones."""

    disponibilidad_choices = [
        ('si', 'Sí'),
        ('no', 'No'),
    ]
    disponibilidad = models.CharField(
        max_length=2,
        choices=disponibilidad_choices,
        default='no',
    )

    def __str__(self):
        return f'{self.disponibilidad}'
class ArticuloPanol(models.Model):
    """Stock de un artículo en un pañol."""

    panol = models.ForeignKey(Panol, on_delete=models.RESTRICT)
    nombre_articulo = models.CharField(max_length=50)
    descripcion_articulo = models.CharField(max_length=2000)
    cantidad = models.IntegerField()

    def __str__(self):
        return f"{self.nombre_articulo} en {self.panol}"

class ArticuloBodega(models.Model):
    """Stock de un artículo en una bodega."""

    bodega = models.ForeignKey(Bodega, on_delete=models.RESTRICT)
    nombre_articulo = models.CharField(max_length=50)
    descripcion_articulo = models.CharField(max_length=2000)
    cantidad = models.IntegerField()

    def __str__(self):
        return f"{self.nombre_articulo} en {self.bodega}"

class Maquinaria(models.Model):
    """Equipo de la faena. En la práctica `estado` guarda "Activo", "En Mantenimiento" o "Inactivo"."""

    ESTADOS = [
        ('activo', 'Activo'),
        ('mantenimiento', 'En Mantenimiento'),
        ('inactivo', 'Inactivo'),
    ]

    nombre_maquinaria = models.CharField(max_length=255)
    codigo_maquinaria = models.CharField(max_length=100, unique=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='activo')
    fecha_adquisicion = models.DateField()
    area = models.ForeignKey('Area', on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.nombre_maquinaria

class MovimientoArticulo(models.Model):
    """Registro de un traspaso de stock desde una bodega a un pañol."""

    articulo = models.ForeignKey(ArticuloBodega, on_delete=models.CASCADE)
    origen = models.ForeignKey(Bodega, on_delete=models.CASCADE)
    destino = models.ForeignKey(Panol, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    motivo = models.TextField(blank=True, null=True)
    fecha_movimiento = models.DateTimeField(auto_now_add=True)

    @staticmethod
    @transaction.atomic
    def mover_articulo(articulo, destino, cantidad, motivo):
        """
        Traspasa `cantidad` unidades de un artículo de bodega a un pañol y deja registro del movimiento.
        Si el pañol no tiene ese artículo, lo crea con la misma descripción.
        """
        articulo.cantidad -= cantidad
        articulo.save()

        articulo_panol, _ = ArticuloPanol.objects.get_or_create(
            nombre_articulo=articulo.nombre_articulo,
            panol=destino,
            defaults={'descripcion_articulo': articulo.descripcion_articulo, 'cantidad': 0},
        )
        articulo_panol.cantidad = F('cantidad') + cantidad  # Suma en la base de datos, sin condiciones de carrera
        articulo_panol.save()

        return MovimientoArticulo.objects.create(
            articulo=articulo,
            origen=articulo.bodega,
            destino=destino,
            cantidad=cantidad,
            motivo=motivo
        )
    
class RegistroHoras(models.Model):
    """Horas trabajadas y esperadas de un trabajador (o un equipo) en una fecha."""

    maquinaria = models.ForeignKey(Maquinaria, null=True, blank=True, on_delete=models.CASCADE)
    trabajador = models.ForeignKey(Trabajador, null=True, blank=True, on_delete=models.CASCADE)
    area = models.ForeignKey(Area, on_delete=models.CASCADE)
    horas_trabajadas = models.IntegerField()
    horas_esperadas = models.IntegerField(default=40)
    fecha_registro = models.DateField()

class RetiroArticulo(models.Model):
    """Préstamo de un artículo del pañol a un trabajador y su devolución."""

    trabajador = models.ForeignKey(Trabajador, on_delete=models.CASCADE)
    articulo = models.ForeignKey(ArticuloPanol, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    fecha_retiro = models.DateField(auto_now_add=True)
    fecha_devuelta = models.DateField(null=True, blank=True)  # Nueva fecha de devolución
    es_devuelto = models.BooleanField(default=False)  # Estado para identificar devolución

    def clean(self):
        # Validar que no se devuelva más de lo que fue retirado
        if self.cantidad > self.articulo.cantidad:
            raise ValidationError("La cantidad retirada no puede exceder el stock.")

    def __str__(self):
        return f"Retiro: {self.articulo.nombre_articulo} por {self.trabajador.nombre_trabajador}"

class MantenimientoMaquinaria(models.Model):
    """Mantenimiento realizado a un equipo."""

    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE)
    fecha_mantenimiento = models.DateField()
    descripcion = models.TextField()
    realizado_por = models.ForeignKey(Trabajador, on_delete=models.SET_NULL, null=True, related_name="mantenimientos")

    def __str__(self):
        return f"Mantenimiento {self.maquinaria.nombre_maquinaria} el {self.fecha_mantenimiento}"

class TrabajoMaquinaria(models.Model):
    """Uso de un equipo por un trabajador. `horas_trabajadas` se calcula al guardar
    a partir de `fecha_inicio` y `fecha_fin`."""

    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE)
    trabajador = models.ForeignKey(Trabajador, on_delete=models.CASCADE)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    horas_trabajadas = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    descripcion = models.TextField()

    def save(self, *args, **kwargs):
        if self.fecha_inicio and self.fecha_fin:
            duracion = self.fecha_fin - self.fecha_inicio
            self.horas_trabajadas = round(duracion.total_seconds() / 3600, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.trabajador} - {self.maquinaria} ({self.fecha_inicio} a {self.fecha_fin})"

