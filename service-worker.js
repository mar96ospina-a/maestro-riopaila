// Version constant. MUST match index.html (APP_VERSION, visible "v..." text)
// and maestro.html (CONFIG.version, #appVersion span). Bump all four on release.
const CACHE_VERSION = 'v2.5.2'; // Columna TCH RANDOM FOREST (Estimador TCH) en el maestro
const CACHE_NAME = `riopaila-maestro-${CACHE_VERSION}`;
// El sitio se sirve bajo /maestro-riopaila/ en GitHub Pages y bajo / en local, asi
// que la base se deriva del scope del propio SW. Con '/' fijo, el precache pedia
// /index.html (404) y no cacheaba nada: offline solo funcionaba tras navegar con red.
const BASE = new URL('./', self.registration.scope).pathname;

// Archivos esenciales para modo offline
const CRITICAL_URLS = [
  BASE,
  BASE + 'index.html',
  BASE + 'maestro.html',
  BASE + 'maestro.csv',
  BASE + 'zqm.csv',
  BASE + 'manifest.json',
  BASE + 'service-worker.js',
  BASE + 'icon-192.png',
  BASE + 'icon-512.png',
  BASE + 'logo-castilla.png',
  BASE + 'logo-riopaila.png',
  // Tailwind y las fuentes. Antes venían de CDN y el SW ni las veía (son de otro
  // origen), así que offline la app se quedaba sin CSS: sin Tailwind la clase
  // .hidden deja de existir y se destapan a la vez spinner, error, banner y modales.
  BASE + 'vendor/tailwind.js',
  BASE + 'vendor/fonts.css',
  BASE + 'vendor/manrope-latin.woff2',
  BASE + 'vendor/manrope-latin-ext.woff2',
  BASE + 'vendor/material-symbols.woff2'
];

// ===============================
// 1. INSTALAR – Cacheo inicial
// ===============================
self.addEventListener('install', event => {
  console.log('[SW] Instalando versión', CACHE_VERSION);

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async cache => {
        console.log('[SW] Cacheando archivos críticos...');
        // La instalación es TODO O NADA a propósito. Antes cacheaba lo que podía
        // y seguía adelante; con señal intermitente en campo eso producía una
        // caché nueva a medias, y como `activate` borra la anterior, el usuario
        // se quedaba sin app. Si algo falta, preferimos abortar y seguir
        // sirviendo la versión anterior, que funciona.
        const fallidos = [];
        for (const url of CRITICAL_URLS) {
          try {
            const response = await fetch(url, { cache: 'reload' });
            if (response && response.ok) {
              await cache.put(url, response.clone());
            } else {
              fallidos.push(`${url} (HTTP ${response.status})`);
            }
          } catch (err) {
            fallidos.push(`${url} (${err.message})`);
          }
        }
        if (fallidos.length) {
          console.warn('[SW] ⚠ Instalación abortada, faltan recursos:', fallidos);
          throw new Error(`Precache incompleto: ${fallidos.length}/${CRITICAL_URLS.length} fallaron`);
        }
        console.log(`[SW] ✅ ${CRITICAL_URLS.length} recursos cacheados`);
      })
      .then(() => {
        console.log('[SW] Instalación completa. ESPERANDO confirmación del usuario...');
        // CAMBIO CRÍTICO: NO hacer skipWaiting automáticamente
        // return self.skipWaiting(); // <-- REMOVIDO
      })
  );
});

// ===============================
// 2. ACTIVAR – Limpiar viejos caches
// ===============================
self.addEventListener('activate', event => {
  console.log('[SW] Activando versión', CACHE_VERSION);
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(k => {
          if (k !== CACHE_NAME) {
            console.log('[SW] 🗑 Eliminando caché antigua:', k);
            return caches.delete(k);
          }
        })
      );
    }).then(() => {
      console.log('[SW] Tomando control de clientes...');
      return self.clients.claim();
    })
  );
});

// ===============================
// 3. FETCH – Caché primero, siempre
// ===============================
// Regla del proyecto: la app abre desde caché y la red solo sirve para
// refrescar en segundo plano. Nunca al revés.
//
// Antes esto era "red primero, caché si falla", y en campo esa es la peor
// combinación posible: `fetch()` NO rechaza rápido cuando hay una barra de
// señal que no enruta (el caso normal en lote). Se queda esperando el timeout
// del sistema —decenas de segundos— con la pantalla en blanco, aunque la
// respuesta estuviera en caché desde el primer momento. Y como
// `navigator.onLine` devuelve true, la app ni siquiera avisaba que estaba
// offline. Con caché primero, abrir no depende de la red en ningún caso.
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Solo interceptamos peticiones de nuestro propio dominio.
  // (Ya no hay recursos externos: Tailwind y las fuentes viven en vendor/.)
  if (url.origin !== location.origin) return;

  // Solo GET: la caché no aplica a otros métodos.
  if (request.method !== 'GET') return;

  event.respondWith(staleWhileRevalidate(request));
});

// ===============================
// 4. FUNCIONES AUXILIARES
// ===============================

// Estrategia "Stale-While-Revalidate" para TODO lo del propio origen.
async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);

  // 1. ¿Está en caché? Se responde con eso, sin tocar la red.
  //    `ignoreSearch` porque la app se abre como maestro.html?empresa=RIOP y la
  //    entrada precacheada es maestro.html a secas: sin esto, elegir empresa
  //    offline fallaba aunque el archivo estuviera guardado.
  const cached = await cache.match(request, { ignoreSearch: true });

  // 2. Refresco en segundo plano. Nunca bloquea la respuesta y su fallo se
  //    ignora: offline es un estado normal aquí, no un error.
  const refresco = fetch(request)
    .then(res => {
      if (res && res.ok) cache.put(request, res.clone());
      return res;
    })
    .catch(() => null);

  if (cached) return cached;

  // 3. Sin caché no queda más que esperar la red (primera visita).
  const res = await refresco;
  if (res && res.ok) return res;

  // 4. Última red de seguridad para navegaciones: servir el HTML principal.
  if (request.mode === 'navigate' || request.destination === 'document') {
    const fallback = await cache.match(BASE + 'maestro.html') || await cache.match(BASE + 'index.html');
    if (fallback) return fallback;
  }

  return Response.error();
}

// Mensajes desde la UI (Botones de actualizar, etc.)
self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') {
    console.log('[SW] ✅ Usuario confirmó actualización. Activando nueva versión...');
    self.skipWaiting();
  }
});
