/**
 * Principales Variables - Form de consulta
 *
 * Renderiza títulos/descripciones desde /api/traducciones/principales-variables.json
 * y acota min/max de los <input type="date"> consultando
 * /api/endpoints/principales-variables-rango.php.
 *
 * El POST del form va a /api/captcha/variables.php (sin cambios).
 */

(function () {
    'use strict';

    var CONFIG = {
        translationsUrl: '/api/traducciones/principales-variables.json',
        rangoUrl: '/api/endpoints/principales-variables-rango.php',
        containerId: 'principales-variables-datos'
    };

    var translations = {};
    var currentLang = 'es';

    function detectLanguage(container) {
        var lang = container.getAttribute('data-lang');
        if (lang === 'en') return 'en';
        if (window.location.pathname.indexOf('/en/') !== -1) return 'en';
        if (document.documentElement.lang === 'en') return 'en';
        return 'es';
    }

    function t(key) {
        var keys = key.split('.');
        var value = translations[currentLang];
        for (var i = 0; i < keys.length; i++) {
            if (value && typeof value === 'object') {
                value = value[keys[i]];
            } else {
                return key;
            }
        }
        return (typeof value === 'string') ? value : key;
    }

    function buildSerieKey(serie, s1, s2, s3, s4) {
        var parts = [parseInt(serie, 10)];
        [s1, s2, s3, s4].forEach(function (s) {
            var n = parseInt(s, 10);
            if (n > 0) parts.push(n);
        });
        return parts.filter(function (x) { return !isNaN(x) && x > 0; }).join('_');
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function renderTitulosYDescripcion(container, serieKey) {
        var meta = (translations[currentLang].series || {})[serieKey];

        var titulo = container.querySelector('[data-pv-titulo]');
        var subtitulo = container.querySelector('[data-pv-subtitulo]');
        var descripcion = container.querySelector('[data-pv-descripcion]');

        if (!meta) {
            if (titulo) titulo.textContent = t('page.serie_no_encontrada');
            if (descripcion) {
                descripcion.innerHTML =
                    '<p class="parrafo_pag">' + escapeHtml(t('page.serie_no_encontrada_desc')) + '</p>' +
                    '<a href="' + escapeHtml(t('page.back_to_indicators_url')) + '" class="bot_consulta" ' +
                    'style="display:inline-block;padding:10px 20px;text-decoration:none;color:white;margin-top:20px;">' +
                    escapeHtml(t('page.back_to_indicators')) + '</a>';
            }
            // Ocultar form
            var form = document.getElementById('form_variables');
            if (form) form.style.display = 'none';
            var heading = container.querySelector('[data-pv-form-heading]');
            if (heading) heading.style.display = 'none';
            // Cambiar title
            try { document.title = t('page.serie_no_encontrada') + ' | BCRA'; } catch (e) {}
            return false;
        }

        if (titulo) titulo.textContent = meta.titulo || '';
        if (subtitulo) {
            if (meta.subtitulo) {
                subtitulo.querySelector('em').textContent = meta.subtitulo;
                subtitulo.style.display = '';
            } else {
                subtitulo.style.display = 'none';
            }
        }

        if (descripcion) {
            descripcion.innerHTML = renderDescripcionHtml(meta);
        }

        return true;
    }

    function renderDescripcionHtml(meta) {
        // Casos especiales: bandas (7928/7929) usan estructura con lista
        if (meta.piso && meta.techo && meta.dentro) {
            var html = '';
            html += '<p class="parrafo_pag">' + escapeHtml(meta.descripcion || '') + '</p>';
            if (meta.descripcion_extra) {
                html += '<p class="parrafo_pag">' + escapeHtml(meta.descripcion_extra) + '</p>';
            }
            html += '<ul class="lista_pag">';
            html += '<li><span class="parrafo_pag">' + escapeHtml(t('bandas.piso_label')) + '</span>' +
                    '<span class="parrafo_pag">' + escapeHtml(meta.piso) + '</span></li>';
            html += '<li><span class="parrafo_pag">' + escapeHtml(t('bandas.techo_label')) + '</span>' +
                    '<span class="parrafo_pag">' + escapeHtml(meta.techo) + '</span></li>';
            html += '<li><span class="parrafo_pag">' + escapeHtml(t('bandas.dentro_label')) + '</span>' +
                    '<span class="parrafo_pag">' + escapeHtml(meta.dentro) + '</span></li>';
            html += '</ul>';
            if (meta.actualizacion) {
                html += '<p class="parrafo_pag"><strong>' + escapeHtml(meta.actualizacion) + '</strong></p>';
            }
            return html;
        }

        // Caso simple: descripcion + descripcion_extra opcional
        var out = '';
        if (meta.descripcion) {
            out += '<p class="parrafo_pag">' + escapeHtml(meta.descripcion) + '</p>';
        }
        if (meta.descripcion_extra) {
            out += '<p class="parrafo_pag">' + escapeHtml(meta.descripcion_extra) + '</p>';
        }
        return out;
    }

    function setLabels(container) {
        var formHeading = container.querySelector('[data-pv-form-heading]');
        if (formHeading) formHeading.textContent = t('form.consultar_historicas');

        var periodoLabel = container.querySelector('[data-pv-periodo-label]');
        if (periodoLabel) periodoLabel.textContent = t('form.periodo');

        var labelDesde = container.querySelector('[data-pv-label-desde]');
        if (labelDesde) labelDesde.textContent = t('form.fecha_desde');

        var labelHasta = container.querySelector('[data-pv-label-hasta]');
        if (labelHasta) labelHasta.textContent = t('form.fecha_hasta');

        var submit = container.querySelector('[data-pv-submit]');
        if (submit) submit.textContent = t('form.consultar');
    }

    function showErrorBanner(container, message) {
        var banner = container.querySelector('[data-pv-error]');
        if (banner) {
            banner.textContent = message;
            banner.style.display = '';
        }
    }

    function handleUrlError(container) {
        var params = new URLSearchParams(window.location.search);
        var code = params.get('captcha_error') || params.get('data_error');
        if (!code) return;

        var key = 'form.errores.' + code;
        var msg = t(key);
        if (msg === key) msg = t('form.errores.default');
        showErrorBanner(container, msg);
    }

    function loadDateRange(serie) {
        if (!serie) return Promise.resolve(null);
        var url = CONFIG.rangoUrl + '?serie=' + encodeURIComponent(serie);
        return fetch(url)
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                if (data && data.success && data.min_fecha && data.max_fecha) {
                    return { min: data.min_fecha, max: data.max_fecha };
                }
                return null;
            })
            .catch(function (err) {
                console.error('principales-variables-datos-app:', err);
                return null;
            });
    }

    function applyDateRange(rango) {
        var inputs = ['fecha_desde', 'fecha_hasta'];
        inputs.forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            if (rango && rango.min) el.setAttribute('min', rango.min);
            if (rango && rango.max) el.setAttribute('max', rango.max);
        });
    }

    function attachFormValidation() {
        var form = document.getElementById('form_variables');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var fd = document.getElementById('fecha_desde');
            var fh = document.getElementById('fecha_hasta');
            var ts = document.querySelector('[name="cf-turnstile-response"]');
            if (!fd.value || !fh.value) {
                alert(t('form.fechas_faltantes'));
                return;
            }
            if (!ts || !ts.value) {
                alert(t('form.verificar_seguridad'));
                return;
            }
            e.currentTarget.submit();
        });
    }

    async function init() {
        var container = document.getElementById(CONFIG.containerId);
        if (!container) return;

        currentLang = detectLanguage(container);

        try {
            var res = await fetch(CONFIG.translationsUrl);
            translations = await res.json();
        } catch (e) {
            console.error('principales-variables-datos-app: error cargando traducciones', e);
            translations = { es: {}, en: {} };
        }

        setLabels(container);
        handleUrlError(container);

        var serie  = container.getAttribute('data-serie');
        var serie1 = container.getAttribute('data-serie1');
        var serie2 = container.getAttribute('data-serie2');
        var serie3 = container.getAttribute('data-serie3');
        var serie4 = container.getAttribute('data-serie4');

        var key = buildSerieKey(serie, serie1, serie2, serie3, serie4);
        var ok = renderTitulosYDescripcion(container, key);

        if (ok) {
            attachFormValidation();
            var rango = await loadDateRange(serie);
            applyDateRange(rango);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
