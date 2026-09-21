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
  const FONT_STEPS = [0.9, 1, 1.15, 1.3];
  const state = {
    issue: null, latestDate: null, view: "cover", idx: 0, offline: false,
    read: LS.get("read", {}), pin: LS.get("pin", "1234"), parentUnlocked: false,
    font: LS.get("font", 1), dark: LS.get("dark", false), last: LS.get("last", null), history: null,
  };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = iso => { const d = new Date(iso + "T00:00:00"); const days = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"]; return `${days[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`; };
  const imgUrl = im => im ? "data/" + im.src : "";
  const applyPrefs = () => {
    document.documentElement.style.fontSize = (19 * FONT_STEPS[state.font]) + "px";
    document.documentElement.dataset.theme = state.dark ? "dark" : "light";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", state.dark ? "#1E1B17" : "#FFF8EC");
  };

  async function fetchJson(url) {
    try {
      const r = await fetch(url + (url.includes("?") ? "&" : "?") + "t=" + Math.floor(Date.now() / 300000), { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      state.offline = false; return await r.json();
    } catch {
      const c = await caches.match(url).catch(() => null);
      if (c) { state.offline = true; return c.json(); }
      return null;
    }
  }
  const loadIssue = date => fetchJson(date ? `data/issues/${date}.json` : "data/latest.json");
  const isRead = (a, date = state.issue.date) => !!state.read[date]?.[a.id];
  const markRead = a => { (state.read[state.issue.date] ||= {})[a.id] = true; LS.set("read", state.read); };
  const readCount = (iss = state.issue) => iss.articles.filter(a => isRead(a, iss.date)).length;
  const isToday = () => state.issue && state.issue.date === state.latestDate;

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
          <button class="btn small ghost" id="font" title="Cỡ chữ">Aa</button>
          <button class="btn small ghost" id="dark" title="Sáng / tối">${state.dark ? "☀️" : "🌙"}</button>
          <button class="btn small ghost" data-go="history" title="Các số trước">🗓️</button>
          <button class="btn small ghost" data-go="parent" title="Góc cha mẹ">🔒</button>
        </div>
      </header>
      ${state.offline ? '<div class="banner">Đang đọc bản đã tải, chưa có mạng.</div>' : ""}
      ${state.issue && !isToday() && state.view !== "history" ? `<div class="banner old">Đây là số báo cũ · <button class="linkish" id="goLatest">Về số hôm nay</button></div>` : ""}
      ${inner}`;
  }

  function figure(a, i, cls = "") {
    const im = a.images?.[i]; if (!im) return "";
    return `<figure class="fig ${cls}"><img src="${imgUrl(im)}" alt="${esc(im.caption)}" width="${im.w}" height="${im.h}" loading="lazy" data-zoom="${i}">${im.caption ? `<figcaption>${esc(im.caption)}</figcaption>` : ""}</figure>`;
  }

  function viewCover() {
    const iss = state.issue, n = iss.articles.length, rc = readCount();
    const [first, ...rest] = iss.articles;
    const resume = state.last && state.last.date === iss.date && !isRead(iss.articles[state.last.idx] || {}) && rc > 0 && rc < n
      ? `<button class="btn primary" data-open="${state.last.idx}" style="margin-top:12px">▶ Đọc tiếp bài ${state.last.idx + 1}</button>` : "";
    const hero = first ? `
      <button class="hero-card ${isRead(first) ? "read" : ""}" data-open="0">
        ${first.images?.length ? `<img class="hero-img" src="${imgUrl(first.images[first.lead ?? 0])}" alt="">` : `<div class="hero-img placeholder">${first.emoji}</div>`}
        <div class="hero-text"><div class="sec">${first.emoji} ${esc(first.section_name)} · ${esc(first.source_name)}</div><h2>${esc(first.title)}</h2><p>${esc(first.sapo)}</p></div>
        ${isRead(first) ? '<div class="tick">✓</div>' : ""}
      </button>` : "";
    return shell(`
      <section class="cover">
        <div class="date">${fmtDate(iss.date)}</div>
        <h1>${isToday() ? "Số báo hôm nay" : "Số báo này"} có ${n} bài</h1>
        <p>${esc(iss.tagline)}</p>
        <div class="progress"><i style="width:${n ? Math.round(rc / n * 100) : 0}%"></i></div>
        <div class="progress-label">${rc === n ? "Đọc hết rồi! 🎉" : `Đã đọc ${rc}/${n}`}</div>
        ${resume}
      </section>
      ${hero}
      <div class="list">
        ${rest.map((a, k) => `<button class="card ${isRead(a) ? "read" : ""}" data-open="${k + 1}">
            ${a.images?.length ? `<img class="thumb" src="${imgUrl(a.images[a.lead ?? 0])}" alt="" loading="lazy">` : `<div class="thumb placeholder">${a.emoji}</div>`}
            <div><div class="sec">${esc(a.section_name)} · ${esc(a.source_name)}</div><h3>${esc(a.title)}</h3><p>${esc(a.sapo)}</p></div>
            <div class="tick">${isRead(a) ? "✓" : ""}</div>
          </button>`).join("")}
      </div>
      <p class="muted" style="text-align:center;margin-top:26px">${rc === n ? "Muốn đọc thêm? Bấm 🗓️ để xem các số trước." : `Đọc hết ${n} bài là xong. Hẹn mai nhé!`}</p>`);
  }

  function viewArticle() {
    const iss = state.issue, a = iss.articles[state.idx];
    const lead = a.images?.length ? a.lead ?? 0 : null;
    const body = (a.blocks || []).map(b => {
      if (b.t === "img") return b.i === lead ? "" : figure(a, b.i);
      if (b.t === "h") return `<h3>${esc(b.text)}</h3>`;
      if (b.t === "q") return `<blockquote>${esc(b.text)}</blockquote>`;
      if (b.t === "li") return `<p class="li">• ${esc(b.text)}</p>`;
      return `<p>${esc(b.text)}</p>`;
    }).join("");
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
      </article>
      <div class="lightbox" id="lightbox" hidden><img alt=""><div class="cap"></div></div>`, { back: true });
  }

  function viewDone() {
    return shell(`<section class="done"><div class="big">🌟</div><h1>Bạn đọc hết ${state.issue.articles.length} bài!</h1><p>${isToday() ? "Hẹn gặp lại ngày mai với số báo mới nhé." : "Còn nhiều số khác đang chờ."}</p>
      <div class="row" style="justify-content:center"><button class="btn" data-go="cover">Về trang bìa</button><button class="btn primary" data-go="history">🗓️ Các số trước</button></div></section>`);
  }

  function viewHistory() {
    const h = state.history;
    const rows = h == null ? '<p class="muted">Đang tải…</p>' : !h.length ? '<p class="muted">Chưa có số nào khác.</p>' :
      h.map(x => {
        const rc = x.articles ? x.articles.filter(a => isRead(a, x.date)).length : 0, n = x.articles?.length || 0;
        const lead = x.articles?.[0];
        return `<button class="card ${n && rc === n ? "read" : ""}" data-date="${x.date}">
          ${lead?.images?.length ? `<img class="thumb" src="${imgUrl(lead.images[lead.lead ?? 0])}" alt="" loading="lazy">` : `<div class="thumb placeholder">📰</div>`}
          <div><div class="sec">${x.date === state.latestDate ? "Hôm nay" : fmtDate(x.date)}</div><h3>${n} bài · đã đọc ${rc}</h3><p>${esc(lead?.title || "")}</p></div>
          <div class="tick">${n && rc === n ? "✓" : ""}</div></button>`;
      }).join("");
    return shell(`<section class="cover"><div class="date">Các số báo</div><h1>Đọc lại số trước</h1><p>Toàn bộ đều là bài bố mẹ đã duyệt.</p></section><div class="list">${rows}</div>`, { back: true });
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
      <h2>Cài đặt</h2>
      <div class="row"><button class="btn small" id="change-pin">Đổi mã PIN</button><button class="btn small" id="clear-read">Đánh dấu chưa đọc số này</button><button class="btn small" id="clear-all">Xóa dữ liệu trên máy này</button></div>
      <p class="muted" style="margin-top:14px">Sinh lúc ${esc(iss.generated_at || "")}.</p>
      <div style="margin-top:18px"><button class="btn" data-go="cover">← Về báo</button></div></section>`);
  }

  function render() {
    tts.stop(document.getElementById("tts"));
    applyPrefs();
    let html;
    if (!state.issue && state.view !== "history") html = shell(`<div class="empty"><div style="font-size:3rem">📭</div><h2>Chưa có số báo</h2><p>Bố mẹ chưa xuất bản số báo hôm nay, hoặc chưa có mạng lần đầu.</p><div class="row" style="justify-content:center"><button class="btn" id="retry">Thử lại</button><button class="btn" data-go="history">🗓️ Các số trước</button></div></div>`);
    else if (state.view === "parent") html = viewParent();
    else if (state.view === "history") html = viewHistory();
    else if (state.view === "article") html = viewArticle();
    else if (state.view === "done") html = viewDone();
    else html = viewCover();
    $app.innerHTML = html; window.scrollTo({ top: 0 }); bind();
  }

  function bind() {
    $app.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => {
      const v = b.dataset.go;
      if (v === "parent") state.parentUnlocked = false;
      if (v === "history") { state.view = "history"; render(); loadHistory(); return; }
      state.view = v; render();
    }));
    $app.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => {
      state.idx = +b.dataset.open; state.view = "article"; state.last = { date: state.issue.date, idx: state.idx }; LS.set("last", state.last); render();
    }));
    $app.querySelectorAll("[data-date]").forEach(b => b.addEventListener("click", async () => {
      const j = state.history?.find(x => x.date === b.dataset.date && x.articles) || await loadIssue(b.dataset.date);
      if (j) { state.issue = j; state.view = "cover"; render(); }
    }));
    document.getElementById("goLatest")?.addEventListener("click", async () => { const j = await loadIssue(); if (j) { state.issue = j; state.view = "cover"; render(); } });
    document.getElementById("retry")?.addEventListener("click", boot);
    document.getElementById("font")?.addEventListener("click", () => { state.font = (state.font + 1) % FONT_STEPS.length; LS.set("font", state.font); applyPrefs(); });
    document.getElementById("dark")?.addEventListener("click", () => { state.dark = !state.dark; LS.set("dark", state.dark); render(); });

    const a = state.issue?.articles?.[state.idx];
    const ttsBtn = document.getElementById("tts");
    if (ttsBtn && a) ttsBtn.addEventListener("click", () => tts.speak([a.title, a.sapo, ...(a.blocks || []).filter(b => b.text).map(b => b.text)].join(". "), ttsBtn));
    const lb = document.getElementById("lightbox");
    if (lb && a) {
      $app.querySelectorAll("img[data-zoom]").forEach(img => img.addEventListener("click", () => {
        const im = a.images[+img.dataset.zoom]; lb.querySelector("img").src = imgUrl(im); lb.querySelector(".cap").textContent = im.caption || ""; lb.hidden = false; document.body.style.overflow = "hidden";
      }));
      lb.addEventListener("click", () => { lb.hidden = true; document.body.style.overflow = ""; });
    }
    document.getElementById("next")?.addEventListener("click", () => {
      markRead(a);
      const next = state.issue.articles.findIndex((x, i) => i > state.idx && !isRead(x));
      const any = state.issue.articles.findIndex(x => !isRead(x));
      if (next >= 0) { state.idx = next; state.view = "article"; } else if (any >= 0) { state.idx = any; state.view = "article"; } else state.view = "done";
      if (state.view === "article") { state.last = { date: state.issue.date, idx: state.idx }; LS.set("last", state.last); }
      render();
    });
    const pins = [...$app.querySelectorAll("[data-pin]")];
    if (pins.length) {
      pins[0].focus();
      const check = () => { const code = pins.map(p => p.value).join(""); if (code.length !== 4) return;
        if (code === state.pin) { state.parentUnlocked = true; render(); } else { document.getElementById("pin-msg").textContent = "Sai mã, thử lại."; pins.forEach(p => p.value = ""); pins[0].focus(); } };
      pins.forEach((inp, i) => {
        inp.addEventListener("input", () => { const d = inp.value.replace(/\D/g, ""); inp.value = d.slice(0, 1); d.slice(1).split("").forEach((c, k) => { if (pins[i + 1 + k]) pins[i + 1 + k].value = c; }); const ni = Math.min(3, i + Math.max(1, d.length)); if (d && ni > i) pins[ni].focus(); check(); });
        inp.addEventListener("keydown", e => { if (e.key === "Backspace" && !inp.value && i > 0) { pins[i - 1].value = ""; pins[i - 1].focus(); e.preventDefault(); } });
      });
    }
    document.getElementById("change-pin")?.addEventListener("click", () => { const p = prompt("Mã PIN mới (4 số):", ""); if (p && /^\d{4}$/.test(p)) { state.pin = p; LS.set("pin", p); alert("Đã đổi mã."); } });
    document.getElementById("clear-read")?.addEventListener("click", () => { delete state.read[state.issue.date]; LS.set("read", state.read); alert("Đã đánh dấu chưa đọc."); });
    document.getElementById("clear-all")?.addEventListener("click", () => { if (confirm("Xóa tiến độ đọc và cài đặt trên máy này?")) { ["read", "pin", "font", "dark", "last"].forEach(LS.del); location.reload(); } });
  }

  async function loadHistory() {
    const idx = await fetchJson("data/index.json");
    const dates = (idx?.issues || []).slice(0, 30);
    // tải song song tối đa 10 số gần nhất để có ảnh và tiến độ; số cũ hơn chỉ hiện ngày
    const full = await Promise.all(dates.slice(0, 10).map(d => loadIssue(d)));
    state.history = dates.map((d, i) => full[i] || { date: d, articles: null });
    if (state.view === "history") render();
  }

  async function boot() {
    const [issue, idx] = await Promise.all([loadIssue(), fetchJson("data/index.json")]);
    state.latestDate = issue?.date || idx?.issues?.[0] || null;
    state.issue = issue && issue.articles?.length ? issue : null;
    render();
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  boot();
})();
