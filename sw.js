// WH40K Combat Calc Service Worker
// Bump CACHE_VERSION whenever you deploy an update — this forces all clients to refresh
const CACHE_VERSION = 'wh40k-calc-v1';
const ASSETS = [
  './wh40k_combat_calc.html',
  './manifest.json'
];

// Install: cache all assets
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_VERSION).then(function(cache) {
      return cache.addAll(ASSETS);
    }).then(function() {
      // Force this SW to activate immediately (don't wait for old tabs to close)
      return self.skipWaiting();
    })
  );
});

// Activate: delete old caches
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(key) { return key !== CACHE_VERSION; })
            .map(function(key) { return caches.delete(key); })
      );
    }).then(function() {
      // Take control of all open clients immediately
      return self.clients.claim();
    })
  );
});

// Fetch: serve from cache, fall back to network, update cache in background
self.addEventListener('fetch', function(event) {
  event.respondWith(
    caches.open(CACHE_VERSION).then(function(cache) {
      return cache.match(event.request).then(function(cached) {
        var networkFetch = fetch(event.request).then(function(response) {
          // Cache fresh responses for our assets
          if (response.ok && event.request.url.indexOf('chrome-extension') === -1) {
            cache.put(event.request, response.clone());
          }
          return response;
        }).catch(function() {
          return cached; // offline fallback
        });
        // Return cached version immediately if available, update in background
        return cached || networkFetch;
      });
    })
  );
});
