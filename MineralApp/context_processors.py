"""
Context processors de Mineral Manager.

Agregan a todas las plantillas los datos que necesita el layout común
(templates/base.html), para no repetirlos en cada vista.
"""

# Menú lateral: (nombre de la ruta, texto, ícono de Bootstrap Icons, rutas que también lo marcan como activo)
MENU = [
    ('home', 'Inicio', 'bi-speedometer2', ()),
    ('gestion_trabajadores', 'Trabajadores', 'bi-people', ('add_trabajador', 'editar_trabajador')),
    ('maquinaria', 'Maquinaria', 'bi-truck', ('ver_mantenimientos', 'ver_trabajos')),
    ('pañol', 'Pañol', 'bi-tools', ()),
    ('bodega', 'Bodega', 'bi-box-seam', ()),
    ('retiro_articulo', 'Retiro de artículos', 'bi-box-arrow-up-right', ()),
    ('mover_articulo', 'Bodega → Pañol', 'bi-arrow-left-right', ()),
    ('upload_csv', 'Carga de datos', 'bi-cloud-arrow-up', ()),
]


def navegacion(request):
    """
    Devuelve el menú lateral indicando qué ítem corresponde a la página actual.
    """
    ruta_actual = getattr(request.resolver_match, 'url_name', None)
    menu = [
        {
            'ruta': ruta,
            'texto': texto,
            'icono': icono,
            'activo': ruta_actual == ruta or ruta_actual in relacionadas,
        }
        for ruta, texto, icono, relacionadas in MENU
    ]
    return {'menu_principal': menu}
