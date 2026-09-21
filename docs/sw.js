/* Service worker: vỏ app cache sẵn; dữ liệu số báo ưu tiên mạng, mất mạng dùng bản đã tải. */
const SHELL = "btl-shell-v1";
const DATA = "btl-data-v1";
const SHELL_FILES = ["./", "index.html", "app.css", "app.js", "manifest.webmanifest", "icons/icon.svg", "icons/icon-192.png", "icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => ![SHELL, DATA].includes(k)).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;               // font Google: để trình duyệt tự lo
  if (url.pathname.includes("/data/")) {
    // mạng trước, lưu lại; mất mạng → cache (bỏ query ?t=)
    const key = new Request(url.origin + url.pathname);
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) caches.open(DATA).then(c => c.put(key, r.clone()));
      return r;
    }).catch(() => caches.match(key)));
    return;
  }
  // vỏ app: mạng trước để bản mới lên ngay, mất mạng dùng cache
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && e.request.method === "GET") caches.open(SHELL).then(cc => cc.put(e.request, r.clone()));
    return r;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
