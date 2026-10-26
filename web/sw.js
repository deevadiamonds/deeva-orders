/* Deeva Orders service worker: keeps the app shell available offline and shows notifications
   sent by the notification server while the app is closed. Never touches Firestore / Storage traffic. */
const VERSION = 'do-v2';

try {
  importScripts('config.js');
  if (self.DO_CONFIG && self.DO_CONFIG.apiKey && self.DO_CONFIG.vapidKey) {
    importScripts('https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js', 'https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js');
    const c = Object.assign({}, self.DO_CONFIG); delete c.vapidKey;
    firebase.initializeApp(c);
    firebase.messaging();
  }
} catch (e) { /* offline or unsupported: the app still works, just no closed-app notifications */ }

const SHELL = ['./', 'index.html', 'config.js', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/mark.png', 'icons/wordmark.png', 'icons/favicon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;
  const lib = (url.hostname === 'www.gstatic.com' && url.pathname.startsWith('/firebasejs/')) || url.hostname === 'cdnjs.cloudflare.com';
  const fonts = url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (!sameOrigin && !lib && !fonts) return;
  /* the page and its config: network first, so updates arrive as soon as the app is opened */
  if (req.mode === 'navigate' || (sameOrigin && /\/(index\.html|config\.js)?$/.test(url.pathname))) {
    const key = /config\.js$/.test(url.pathname) ? 'config.js' : 'index.html';
    e.respondWith(fetch(req).then(r => { const copy = r.clone(); caches.open(VERSION).then(c => c.put(key, copy)); return r; })
      .catch(() => caches.match(key)));
    return;
  }
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(r => { if (r && (r.ok || r.type === 'opaque')) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(req, copy)); } return r; }).catch(() => hit);
    return hit || net;
  }));
});
self.addEventListener('notificationclick', e => {
  if (e.notification.data && e.notification.data.FCM_MSG) return; /* Firebase opens its own link */
  e.notification.close();
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    for (const c of list) { if ('focus' in c) return c.focus(); }
    return self.clients.openWindow('./');
  }));
});
