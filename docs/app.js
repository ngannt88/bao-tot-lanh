/* Báo Tốt Lành — app đọc cho con. Bài hiện NGUYÊN VĂN báo gốc đã được bố mẹ duyệt.
   Không link ra ngoài trong chế độ trẻ em. Dữ liệu riêng lưu tại máy. */
(() => {
  "use strict";
  const $app = document.getElementById("app");
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const state = { issue: null, view: "cover", idx: 0, offline: false, read: LS.get("read", {}), pin: LS.get("pin", "1234"), parentUnlocked: false };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = iso => { const d = new Date(iso + "T00:00:00"); const days = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"]; return `${days[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`; };
  const imgUrl = im => im ? "data/" + im.src : "";

  async function loadIssue(date) {
    const url = date ? `data/issues/${date}.json` : "data/latest.json";
    try {
      const r = await fetch(url + "?t=" + Math.floor(Date.now() / 300000), { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      state.offline = false; return await r.json();
    } catch {
      const c = await caches.match(url).catch(() => null);
      if (c) { state.offline = true; return c.json(); }
      return null;
    }
  }
  const isRead = a => !!state.read[state.issue.date]?.[a.id];
  const markRead = a => { (state.read[state.issue.date] ||= {})[a.id] = true; LS.set("read", state.read); };
  const readCount = () => state.issue.articles.filter(isRead).length;

  const tts = {
    on: false,
    speak(text, btn) {
      if (!("speechSynthesis" in window)) { btn.textContent = "Máy này chưa đọc được"; btn.disabled = true; return; }
      if (this.on) return this.stop(btn);
      const u = new SpeechSynthesisUtterance(text);
      const v = speechSynthesis.getVoices().find(v => /^vi/i.test(v.lang)); if (v) u.voice = v;
      u.lang = "vi-VN"; u.rate = 0.95; u.onend = u.onerror = () => this.stop(btn);
      speechSynthesis.cancel(); speechSynthesis.speak(u); this.on = true; btn.classList.add("speaking"); btn.innerHTML = "⏹ Dừng đọc";
    },
    stop(btn) { window.speechSynthesis?.cancel(); this.on = false; if (btn) { btn.classList.remove("speaking"); btn.innerHTML = "🔊 Đọc cho tớ nghe"; } },
  };

  function shell(inner, opts = {}) {
    return `
      <header class="top">
        <div class="brand"><img src="icons/icon.svg" alt=""><div>${esc(state.issue?.paper || "Báo Tốt Lành")}<small>${state.issue ? fmtDate(state.issue.date) : ""}</small></div></div>
        <div class="right">
          ${opts.back ? `<button class="btn small" data-go="cover">← Trang bìa</button>` : ""}
          <button class="btn small ghost" data-go="parent" title="Góc cha mẹ">🔒</button>
        </div>
      </header>
      ${state.offline ? '<div class="banner">Đang đọc bản đã tải, chưa có mạng.</div>' : ""}
      ${inner}`;
  }

  function figure(a, i, cls = "") {
    const im = a.images?.[i]; if (!im) return "";
    return `<figure class="fig ${cls}"><img src="${imgUrl(im)}" alt="${esc(im.caption)}" width="${im.w}" height="${im.h}" loading="lazy">${im.caption ? `<figcaption>${esc(im.caption)}</figcaption>` : ""}</figure>`;
  }

  function viewCover() {
    const iss = state.issue, n = iss.articles.length, rc = readCount();
    const [first, ...rest] = iss.articles;
    const hero = first ? `
      <button class="hero-card ${isRead(first) ? "read" : ""}" data-open="0">
        ${first.images?.length ? `<img class="hero-img" src="${imgUrl(first.images[first.lead ?? 0])}" alt="">` : `<div class="hero-img placeholder">${first.emoji}</div>`}
        <div class="hero-text"><div class="sec">${first.emoji} ${esc(first.section_name)} · ${esc(first.source_name)}</div><h2>${esc(first.title)}</h2><p>${esc(first.sapo)}</p></div>
        ${isRead(first) ? '<div class="tick">✓</div>' : ""}
      </button>` : "";
    return shell(`
      <section class="cover">
        <div class="date">${fmtDate(iss.date)}</div>
        <h1>Số báo hôm nay có ${n} bài</h1>
        <p>${esc(iss.tagline)}</p>
        <div class="progress"><i style="width:${n ? Math.round(rc / n * 100) : 0}%"></i></div>
        <div class="progress-label">${rc === n ? "Đọc hết rồi! 🎉" : `Đã đọc ${rc}/${n}`}</div>
      </section>
      ${hero}
      <div class="list">
        ${rest.map((a, k) => `<button class="card ${isRead(a) ? "read" : ""}" data-open="${k + 1}">
            ${a.images?.length ? `<img class="thumb" src="${imgUrl(a.images[a.lead ?? 0])}" alt="" loading="lazy">` : `<div class="thumb placeholder">${a.emoji}</div>`}
            <div><div class="sec">${esc(a.section_name)} · ${esc(a.source_name)}</div><h3>${esc(a.title)}</h3><p>${esc(a.sapo)}</p></div>
            <div class="tick">${isRead(a) ? "✓" : ""}</div>
          </button>`).join("")}
      </div>
      <p class="muted" style="text-align:center;margin-top:26px">Đọc hết ${n} bài là xong. Hẹn mai nhé!</p>`);
  }

  function viewArticle() {
    const iss = state.issue, a = iss.articles[state.idx];
    const lead = a.images?.length ? a.lead ?? 0 : null;
    const usedLead = new Set();
    const body = (a.blocks || []).map(b => {
      if (b.t === "img") { if (b.i === lead) { usedLead.add(b.i); return ""; } return figure(a, b.i); }
      if (b.t === "h") return `<h3>${esc(b.text)}</h3>`;
      if (b.t === "q") return `<blockquote>${esc(b.text)}</blockquote>`;
      if (b.t === "li") return `<p class="li">• ${esc(b.text)}</p>`;
      return `<p>${esc(b.text)}</p>`;
    }).join("");
    const plain = [a.title, a.sapo, ...(a.blocks || []).filter(b => b.text).map(b => b.text)].join(". ");
    return shell(`
      <article class="article">
        <div class="sec">${a.emoji} ${esc(a.section_name)} · Bài ${state.idx + 1}/${iss.articles.length}</div>
        <h1>${esc(a.title)}</h1>
        ${a.sapo ? `<p class="lead">${esc(a.sapo)}</p>` : ""}
        <div class="byline">${esc(a.source_name)}${a.author ? " · " + esc(a.author) : ""}</div>
        ${lead != null ? figure(a, lead, "lead-fig") : ""}
        <div class="tools"><button class="btn small" id="tts">🔊 Đọc cho tớ nghe</button></div>
        <div class="body">${body}</div>
        <div class="byline end">Theo ${esc(a.source_name)}${a.author ? " · " + esc(a.author) : ""}</div>
        <div class="nav">
          <button class="btn" data-go="cover">☰ Trang bìa</button>
          <button class="btn primary" id="next">${state.idx + 1 < iss.articles.length ? "Đọc xong, bài tiếp →" : "Đọc xong 🎉"}</button>
        </div>
      </article>`, { back: true });
    void plain;
  }

  function viewDone() {
    return shell(`<section class="done"><div class="big">🌟</div><h1>Hôm nay bạn đọc hết ${state.issue.articles.length} bài!</h1><p>Hẹn gặp lại ngày mai với số báo mới nhé.</p><button class="btn" data-go="cover">Về trang bìa</button></section>`);
  }

  function viewParent() {
    if (!state.parentUnlocked) {
      return shell(`<section class="done"><div class="big">🔒</div><h1>Góc cha mẹ</h1><p>Nhập mã 4 số</p>
        <div class="pin">${[0, 1, 2, 3].map(i => `<input inputmode="numeric" maxlength="1" pattern="[0-9]" data-pin="${i}" aria-label="số ${i + 1}">`).join("")}</div>
        <div class="muted" id="pin-msg">Mã mặc định 1234, đổi được ở trong.</div>
        <div style="margin-top:14px"><button class="btn" data-go="cover">Quay lại</button></div></section>`);
    }
    const iss = state.issue;
    return shell(`<section class="parent">
      <h2>Số báo ${fmtDate(iss.date)} — nguồn để đối chiếu</h2>
      <p class="muted">Trẻ không thấy phần này. Bài được duyệt tại máy tính qua trang <code>duyet.html</code>.</p>
      <table><tr><th>Mục</th><th>Bài</th><th>Nguồn</th><th>Điểm AI</th></tr>
        ${iss.articles.map(a => `<tr><td>${a.emoji} ${esc(a.section_name)}</td><td>${esc(a.title)}</td><td><a href="${esc(a.source_url)}" target="_blank" rel="noopener">${esc(a.source_name)}</a></td><td>${a.score ?? "–"}</td></tr>`).join("")}
      </table>
      <h2>Các số báo trước</h2><div class="row" id="history"><span class="muted">Đang tải…</span></div>
      <h2>Cài đặt</h2>
      <div class="row"><button class="btn small" id="change-pin">Đổi mã PIN</button><button class="btn small" id="clear-read">Đánh dấu chưa đọc hôm nay</button><button class="btn small" id="clear-all">Xóa dữ liệu trên máy này</button></div>
      <p class="muted" style="margin-top:14px">Sinh lúc ${esc(iss.generated_at || "")}.</p>
      <div style="margin-top:18px"><button class="btn" data-go="cover">← Về báo</button></div></section>`);
  }

  function render() {
    tts.stop(document.getElementById("tts"));
    let html;
    if (!state.issue) html = shell(`<div class="empty"><div style="font-size:3rem">📭</div><h2>Chưa có số báo</h2><p>Bố mẹ chưa xuất bản số báo hôm nay, hoặc chưa có mạng lần đầu.</p><button class="btn" id="retry">Thử lại</button></div>`);
    else if (state.view === "parent") html = viewParent();
    else if (state.view === "article") html = viewArticle();
    else if (state.view === "done") html = viewDone();
    else html = viewCover();
    $app.innerHTML = html; window.scrollTo({ top: 0 }); bind();
  }

  function bind() {
    $app.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => { if (b.dataset.go === "parent") state.parentUnlocked = false; state.view = b.dataset.go; render(); }));
    $app.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => { state.idx = +b.dataset.open; state.view = "article"; render(); }));
    document.getElementById("retry")?.addEventListener("click", boot);
    const a = state.issue?.articles?.[state.idx];
    const ttsBtn = document.getElementById("tts");
    if (ttsBtn && a) ttsBtn.addEventListener("click", () => tts.speak([a.title, a.sapo, ...(a.blocks || []).filter(b => b.text).map(b => b.text)].join(". "), ttsBtn));
    document.getElementById("next")?.addEventListener("click", () => {
      markRead(a);
      const next = state.issue.articles.findIndex((x, i) => i > state.idx && !isRead(x));
      const any = state.issue.articles.findIndex(x => !isRead(x));
      if (next >= 0) { state.idx = next; state.view = "article"; } else if (any >= 0) { state.idx = any; state.view = "article"; } else state.view = "done";
      render();
    });
    const pins = [...$app.querySelectorAll("[data-pin]")];
    if (pins.length) {
      pins[0].focus();
      const check = () => { const code = pins.map(p => p.value).join(""); if (code.length !== 4) return;
        if (code === state.pin) { state.parentUnlocked = true; render(); loadHistory(); } else { document.getElementById("pin-msg").textContent = "Sai mã, thử lại."; pins.forEach(p => p.value = ""); pins[0].focus(); } };
      pins.forEach((inp, i) => {
        inp.addEventListener("input", () => { const d = inp.value.replace(/\D/g, ""); inp.value = d.slice(0, 1); d.slice(1).split("").forEach((c, k) => { if (pins[i + 1 + k]) pins[i + 1 + k].value = c; }); const ni = Math.min(3, i + Math.max(1, d.length)); if (d && ni > i) pins[ni].focus(); check(); });
        inp.addEventListener("keydown", e => { if (e.key === "Backspace" && !inp.value && i > 0) { pins[i - 1].value = ""; pins[i - 1].focus(); e.preventDefault(); } });
      });
    }
    if (state.parentUnlocked && state.view === "parent") loadHistory();
    document.getElementById("change-pin")?.addEventListener("click", () => { const p = prompt("Mã PIN mới (4 số):", ""); if (p && /^\d{4}$/.test(p)) { state.pin = p; LS.set("pin", p); alert("Đã đổi mã."); } });
    document.getElementById("clear-read")?.addEventListener("click", () => { delete state.read[state.issue.date]; LS.set("read", state.read); alert("Đã đánh dấu chưa đọc."); });
    document.getElementById("clear-all")?.addEventListener("click", () => { if (confirm("Xóa tiến độ đọc và cài đặt trên máy này?")) { ["read", "pin"].forEach(LS.del); location.reload(); } });
  }

  async function loadHistory() {
    const el = document.getElementById("history"); if (!el) return;
    try {
      const idx = await (await fetch("data/index.json", { cache: "no-cache" })).json();
      const dates = (idx.issues || []).filter(d => d !== state.issue.date).slice(0, 14);
      el.innerHTML = dates.length ? dates.map(d => `<button class="btn small" data-date="${d}">${d}</button>`).join("") : '<span class="muted">Chưa có số nào trước.</span>';
      el.querySelectorAll("[data-date]").forEach(b => b.addEventListener("click", async () => { const j = await loadIssue(b.dataset.date); if (j) { state.issue = j; state.view = "cover"; render(); } }));
    } catch { el.innerHTML = '<span class="muted">Không tải được danh mục.</span>'; }
  }

  async function boot() { state.issue = await loadIssue(); if (state.issue && !state.issue.articles?.length) state.issue = null; render(); }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  boot();
})();
