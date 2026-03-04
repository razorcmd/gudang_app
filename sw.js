self.addEventListener('install', (e) => {
    console.log('[Service Worker] Install');
});

self.addEventListener('fetch', (e) => {
    // Biarkan aplikasi selalu mengambil data terbaru dari server (Network First)
    e.respondWith(fetch(e.request));
});