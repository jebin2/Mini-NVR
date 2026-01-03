// Minimal Service Worker for PWA installability
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Only handle requests to the same origin (ignore Google API calls etc)
    if (new URL(event.request.url).origin !== self.location.origin) {
        return;
    }

    // Network-only strategy for now to avoid stale cache issues with Vite build
    event.respondWith(fetch(event.request));
});
