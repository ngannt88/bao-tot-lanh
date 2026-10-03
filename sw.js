/* Service worker: vỏ app cache sẵn; dữ liệu số báo ưu tiên mạng, mất mạng dùng bản đã tải.

   Lưu ý đã trả giá: việc ghi vào cache PHẢI nằm trong event.waitUntil(), nếu không trình duyệt
   có quyền hủy tác vụ ngay khi fetch event kết thúc và cache sẽ rỗng — mất chế độ đọc offline.
*/
const SHELL = "btl-shell-v2";
const DATA = "btl-data-v2";
const SHELL_FILES = ["./", "index.html", "app.css", "app.js", "manifest.webmanifest", "icons/icon.svg", "icons/icon-192.png", "icons/icon-512.png"];
const MAX_DATA_ENTRIES = 400;          // đủ cho vài số báo kèm ảnh, không để phình vô hạn

self.addEventListener("install", e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => ![SHELL, DATA].includes(k)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function trim(cache) {
  const keys = await cache.keys();
  if (keys.length > MAX_DATA_ENTRIES) {
    for (const k of keys.slice(0, keys.length - MAX_DATA_ENTRIES)) await cache.delete(k);
  }
}

async function networkFirst(event, key) {
  const cache = await caches.open(DATA);
  try {
    const res = await fetch(event.request);
    if (res && res.ok) {
      await cache.put(key, res.clone());     // await, không "bắn rồi quên"
      trim(cache);
    }
    return res;
  } catch (err) {
    const hit = await cache.match(key);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirstShell(request) {
  const hit = await caches.match(request, { ignoreSearch: true });
  try {
    const res = await fetch(request);
    if (res && res.ok && request.method === "GET") {
      const c = await caches.open(SHELL);
      await c.put(request, res.clone());
    }
    return res;
  } catch (err) {
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.origin !== location.origin) return;          // font Google: để trình duyệt tự lo
  // File giọng đọc rất nặng (mỗi bài ~1,6 MB): để trình duyệt tự xử lý, KHÔNG đưa vào cache
  // của app, tránh làm đầy bộ nhớ máy tính bảng.
  if (url.pathname.endsWith(".mp3")) return;
  if (url.pathname.includes("/data/")) {
    const key = new Request(url.origin + url.pathname);  // bỏ ?t= để mỗi tệp chỉ có một mục
    e.respondWith(networkFirst(e, key));
    return;
  }
  e.respondWith(cacheFirstShell(e.request));
});
