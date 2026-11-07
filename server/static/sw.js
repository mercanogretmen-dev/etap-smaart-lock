// ETAP Akıllı Kilit - Service Worker (PWA Desteği & Çevrimdışı Mod)
const CACHE_NAME = 'etap-smartlock-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
  '/icons/favicon.png'
];

// 1. Kurulum: Statik kaynakları önbelleğe al
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('📦 [PWA Service Worker] Statik dosyalar önbelleğe alınıyor...');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// 2. Etkinleştirme: Eski önbellekleri temizle
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('🧹 [PWA Service Worker] Eski önbellek temizleniyor:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. İstek Yakalama (Fetch):
// Canlı API çağrıları (/api/) doğrudan ağa gider.
// Statik dosyalar için Network-First (Önce Ağ, İnternet Yoksa Önbellek) stratejisi uygulanır.
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Canlı API ve WebSocket bağlantılarını önbelleğe alma!
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Ağdan başarıyla geldiyse önbelleği güncelle ve yanıtı dön
        if (networkResponse && networkResponse.status === 200 && event.request.method === 'GET') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // İnternet kesilirse veya telefon çekmezse önbellekten getir (Offline Mode)
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // Sayfa isteğiyse ana sayfayı dön
          if (event.request.mode === 'navigate') {
            return caches.match('/');
          }
        });
      })
  );
});
