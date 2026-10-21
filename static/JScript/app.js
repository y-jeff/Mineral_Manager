/*
 * Mineral Manager — comportamiento común a todas las páginas.
 * Se carga desde base.html y auth_base.html.
 */

/** Muestra u oculta la contraseña de un campo (botón con ícono de ojo). */
function togglePassword(inputId, boton) {
    const campo = document.getElementById(inputId);
    const icono = boton.querySelector('i');
    const visible = campo.type === 'text';
    campo.type = visible ? 'password' : 'text';
    icono.classList.toggle('bi-eye', visible);
    icono.classList.toggle('bi-eye-slash', !visible);
}

/** Lee el valor de una cookie (se usa para el token CSRF en peticiones fetch). */
function getCookie(nombre) {
    const cookie = document.cookie.split('; ').find(c => c.startsWith(nombre + '='));
    return cookie ? decodeURIComponent(cookie.split('=')[1]) : null;
}

/**
 * Envía un POST con JSON y token CSRF. Devuelve la respuesta ya convertida a objeto.
 * Lo usan las acciones que no recargan la página (eliminar trabajador, certificaciones, etc.).
 */
async function postJSON(url, datos = {}) {
    const respuesta = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
        body: JSON.stringify(datos),
    });
    return respuesta.json();
}

document.addEventListener('DOMContentLoaded', () => {
    // Formularios con data-confirm piden confirmación antes de enviarse
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', evento => {
            if (!confirm(form.dataset.confirm)) evento.preventDefault();
        });
    });

    // Botones con data-loading se deshabilitan al enviar, para evitar envíos dobles
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', evento => {
            if (evento.defaultPrevented) return;
            const boton = form.querySelector('button[type=submit][data-loading]');
            if (boton) {
                boton.disabled = true;
                boton.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${boton.dataset.loading}`;
            }
        });
    });
});
