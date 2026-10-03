const CACHE_VERSION = 'chem-quiz-v2'
const scopeUrl = new URL('./', self.registration.scope)
const shellUrls = [
  new URL('./', scopeUrl).href,
  new URL('./index.html', scopeUrl).href,
  new URL('./manifest.webmanifest', scopeUrl).href,
  new URL('./icons/icon-192.png', scopeUrl).href,
  new URL('./icons/icon-512.png', scopeUrl).href,
  new URL('./icons/apple-touch-icon.png', scopeUrl).href,
  new URL('./question-bank/bank.json', scopeUrl).href,
]

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_VERSION).then((cache) => cache.addAll(shellUrls)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))),
    ),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy))
          return response
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match(new URL('./index.html', scopeUrl).href))),
    )
    return
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy))
          }
          return response
        })
        .catch(() => cached)
      return cached || network
    }),
  )
})
