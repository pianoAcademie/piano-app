const CACHE_VERSION = "pa-prof-v1";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("pa-prof-") && key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

// Authenticated professor data must always come from the server. The service
// worker exists for installability and deliberately does not cache responses.
self.addEventListener("fetch", (event) => {
  if (event.request.method === "GET" && event.request.url.startsWith(self.location.origin)) {
    event.respondWith(fetch(event.request));
  }
});
