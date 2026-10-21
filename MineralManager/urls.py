"""
Rutas de Mineral Manager.

Los nombres de cada ruta (name=...) son los que usan las plantillas con {% url %}.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import path

from MineralApp import views


def access_denied(request):
    """Página que se muestra cuando el usuario no tiene permisos."""
    return render(request, 'access_denied.html', status=403)


urlpatterns = [
    path('admin/', admin.site.urls),

    # Acceso
    path('', views.login_signup_view, name='login_signup'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login_signup'), name='logout'),
    path('access_denied/', access_denied, name='access_denied'),

    # Recuperación de contraseña (vistas de Django con plantillas propias)
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'), name='password_reset_complete'),

    # Panel principal y carga de datos
    path('home/', views.index, name='home'),
    path('upload/', views.upload_csv, name='upload_csv'),
    path('upload/ejemplo.xlsx', views.descargar_excel_ejemplo, name='descargar_excel_ejemplo'),

    # Trabajadores y certificaciones
    path('trabajadores/', views.trabajadores_view, name='gestion_trabajadores'),
    path('trabajadores/agregar/', views.add_trabajador_view, name='add_trabajador'),
    path('trabajadores/editar/<str:rut>/', views.editar_trabajador, name='editar_trabajador'),
    path('trabajadores/eliminar/', views.eliminar_trabajador, name='eliminar_trabajador'),
    path('trabajadores/descargar_informe/', views.descargar_informe_trabajadores, name='descargar_informe_trabajadores'),
    path('trabajadores/certificaciones/agregar/', views.agregar_capacitacion, name='agregar_capacitacion'),
    path('trabajadores/eliminar_certificacion/<int:cert_id>/', views.eliminar_certificacion, name='eliminar_certificacion'),

    # Inventario: pañol, bodega, traspasos y retiros
    path('pañol/', views.panol_view, name='pañol'),
    path('panol/descargar_informe/', views.descargar_informe_pañol, name='descargar_informe_pañol'),
    path('bodega/', views.bodega_view, name='bodega'),
    path('bodega/descargar_informe/', views.descargar_informe_bodega, name='descargar_informe_bodega'),
    path('articulobodega/', views.mover_articulo_view, name='mover_articulo'),
    path('api/articulos/<int:bodega_id>/', views.obtener_articulos_por_bodega, name='obtener_articulos_por_bodega'),
    path('retiro/', views.retiro_articulo_view, name='retiro_articulo'),
    path('devolver/<int:retiro_id>/', views.devolver_articulo, name='devolver_articulo'),

    # Maquinaria
    path('maquinaria/', views.maquinaria_view, name='maquinaria'),
    path('maquinaria/editar/<int:maquinaria_id>/', views.edit_maquinaria, name='edit_maquinaria'),
    path('maquinaria/desactivar/<int:maquinaria_id>/', views.desactivar_maquinaria, name='desactivar_maquinaria'),
    path('maquinaria/agregar-mantenimiento/', views.add_mantenimiento, name='add_mantenimiento'),
    path('maquinaria/agregar-trabajo/', views.add_trabajo_maquinaria, name='add_trabajo_maquinaria'),
    path('maquinaria/mantenimientos/<int:maquinaria_id>/', views.ver_mantenimientos, name='ver_mantenimientos'),
    path('maquinaria/trabajos/<int:maquinaria_id>/', views.ver_trabajos, name='ver_trabajos'),
]
