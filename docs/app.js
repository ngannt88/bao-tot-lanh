/* Báo Tốt Lành — app đọc. Không link ra ngoài trong chế độ trẻ em. Dữ liệu riêng lưu tại máy. */
(() => {
  "use strict";
  const $app = document.getElementById("app");
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* riêng tư / đầy bộ nhớ: bỏ qua */ } },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const state = {
    issue: null, reader: LS.get("reader", null), view: "cover", idx: 0, offline: false,
    read: LS.get("read", {}),          // {issueDate: {articleId: true}}
    answers: LS.get("answers", {}),    // {issueDate: {articleId: {reader, text, at}}}
    pin: LS.get("pin", "1234"),
    parentUnlocked: false,
  };
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = iso => {
    const d = new Date(iso + "T00:00:00");
    const days = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];
    return `${days[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
  };
  const ACT_META = {
    ve: { icon: "🖍️", name: "Góc vẽ hôm nay" },
    xay: { icon: "🧱", name: "Thử thách xây" },
    thu: { icon: "🧪", name: "Thử tại nhà" },
    hoi: { icon: "💭", name: "Câu hỏi suy nghĩ" },
  };

  // ---------- Dữ liệu ----------
  async function loadIssue(date) {
    const url = date ? `data/issues/${date}.json` : "data/latest.json";
    try {
      const r = await fetch(url + "?t=" + Math.floor(Date.now() / 600000), { cache: "no-cache" });
      if (!r.ok) throw new Error(r.status);
      const j = await r.json();
      state.offline = false;
      return j;
    } catch {
      const c = await caches.match(url).catch(() => null);
      if (c) { state.offline = true; return c.json(); }
      return null;
    }
  }
  function version(a) { return a.versions?.[state.reader] || Object.values(a.versions || {})[0] || {}; }
  function isRead(a) { return !!state.read[state.issue.date]?.[a.id]; }
  function markRead(a) {
    state.read[state.issue.date] = state.read[state.issue.date] || {};
    state.read[state.issue.date][a.id] = true;
    LS.set("read", state.read);
  }
  function readCount() { return state.issue.articles.filter(isRead).length; }

  // ---------- Đọc thành tiếng ----------
  const tts = {
    on: false,
    speak(text, btn) {
      if (!("speechSynthesis" in window)) { btn.textContent = "Máy này chưa đọc được"; btn.disabled = true; return; }
      if (this.on) { this.stop(btn); return; }
      const u = new SpeechSynthesisUtterance(text);
      const v = speechSynthesis.getVoices().find(v => /^vi/i.test(v.lang));
      if (v) u.voice = v;
      u.lang = "vi-VN"; u.rate = state.reader === "be-nho" ? 0.9 : 1;
      u.onend = u.onerror = () => this.stop(btn);
      speechSynthesis.cancel(); speechSynthesis.speak(u);
      this.on = true; btn.classList.add("speaking"); btn.innerHTML = "⏹ Dừng đọc";
    },
    stop(btn) { speechSynthesis?.cancel(); this.on = false; if (btn) { btn.classList.remove("speaking"); btn.innerHTML = "🔊 Đọc cho tớ nghe"; } },
  };

  // ---------- Khung ----------
  function shell(inner, opts = {}) {
    const rc = readCount?.() ?? 0;
    return `
      <header class="top">
        <div class="brand"><img src="icons/icon.svg" alt=""><div>${esc(state.issue?.paper || "Báo Tốt Lành")}<small>${state.issue ? fmtDate(state.issue.date) : ""}</small></div></div>
        <div class="right">
          ${opts.back ? `<button class="btn small" data-go="${opts.back}">← ${opts.backLabel || "Trang bìa"}</button>` : ""}
          ${state.reader && !opts.hideReader ? `<button class="btn small ghost" data-go="pick" title="Đổi người đọc">${state.reader === "be-nho" ? "🧒" : "👦"}</button>` : ""}
          <button class="btn small ghost" data-go="parent" title="Góc cha mẹ">🔒</button>
        </div>
      </header>
      ${state.offline ? '<div class="banner">Đang đọc bản đã tải, chưa có mạng.</div>' : ""}
      ${inner}`;
  }

  // ---------- Màn hình ----------
  function viewPick() {
    const readers = state.issue?.readers || [{ id: "be-nho", name: "Bé 7", age: 7 }, { id: "be-lon", name: "Bé 11", age: 11 }];
    return shell(`
      <section class="hero">
        <div style="font-size:3.5rem">📰</div>
        <h1>Hôm nay ai đọc báo?</h1>
        <p>${esc(state.issue?.tagline || "")}</p>
        <div class="readers">
          ${readers.map(r => `
            <button class="reader-card" data-reader="${esc(r.id)}">
              <div class="big">${r.id === "be-nho" ? "🧒" : "👦"}</div>
              <h2>${esc(r.name)}</h2><p>${r.age} tuổi</p>
            </button>`).join("")}
        </div>
      </section>`, { hideReader: true });
  }

  function viewCover() {
    const iss = state.issue, n = iss.articles.length, rc = readCount();
    return shell(`
      <section class="cover">
        <div class="date">${fmtDate(iss.date)}</div>
        <h1>Số báo hôm nay có ${n} bài</h1>
        <p>${esc(iss.tagline)}</p>
        <div class="progress"><i style="width:${Math.round(rc / n * 100)}%"></i></div>
        <div class="progress-label">${rc === n ? "Đọc hết rồi! 🎉" : `Đã đọc ${rc}/${n}`}</div>
      </section>
      <div class="list">
        ${iss.articles.map((a, i) => {
          const v = version(a);
          return `<button class="card ${isRead(a) ? "read" : ""}" data-open="${i}">
            <div class="emoji">${a.emoji || "📰"}</div>
            <div><div class="sec">${esc(a.section_name)}</div><h3>${esc(v.title)}</h3><p>${esc(v.lead)}</p></div>
            <div class="tick">${isRead(a) ? "✓" : ""}</div>
          </button>`;
        }).join("")}
      </div>
      ${rc === n ? `<div style="text-align:center;margin-top:22px"><button class="btn primary" data-go="done">Xem lại hôm nay 🎉</button></div>` : ""}
      <p class="muted" style="text-align:center;margin-top:26px">Đọc hết ${n} bài là xong. Hẹn mai nhé!</p>`);
  }

  function viewArticle() {
    const iss = state.issue, a = iss.articles[state.idx], v = version(a);
    const ans = state.answers[iss.date]?.[a.id]?.text || "";
    const acts = (a.activities || []).filter(x => x.type !== "hoi");
    const paras = String(v.body || "").split(/\n{2,}|\n/).filter(Boolean);
    return shell(`
      <article class="article" data-aid="${esc(a.id)}">
        <div class="sec">${a.emoji || ""} ${esc(a.section_name)} · Bài ${state.idx + 1}/${iss.articles.length}</div>
        <h1>${esc(v.title)}</h1>
        <p class="lead">${esc(v.lead)}</p>
        <div class="figure"><span class="big">${a.emoji || "📰"}</span>${esc(a.image_alt || "")}</div>
        <div class="tools">
          <button class="btn small" id="tts">🔊 Đọc cho tớ nghe</button>
        </div>
        <div class="body">${paras.map(p => `<p>${esc(p)}</p>`).join("")}</div>
        ${(v.words || []).length ? `<div class="box words"><h4>✨ Từ hay hôm nay <span class="muted">(chạm để xem nghĩa)</span></h4>
          ${v.words.map(w => `<span class="chip"><b>${esc(w.w)}</b><span class="m"> — ${esc(w.m)}</span></span>`).join("")}</div>` : ""}
        ${acts.map(x => { const m = ACT_META[x.type] || { icon: "⭐", name: "Hoạt động" };
          return `<div class="box act"><h4>${m.icon} ${m.name}</h4><p>${esc(x.text)}</p></div>`; }).join("")}
        ${a.fun_fact ? `<div class="box fun"><h4>💡 Bạn có biết?</h4><p style="margin:0">${esc(a.fun_fact)}</p></div>` : ""}
        <div class="box"><h4>💭 Câu hỏi suy nghĩ</h4><p style="margin:0 0 10px">${esc(a.question)}</p>
          <textarea class="answer" id="answer" placeholder="Viết một câu, hoặc nói với bố mẹ cũng được…">${esc(ans)}</textarea>
          <div class="saved" id="saved">${ans ? "Đã lưu câu trả lời của bạn." : ""}</div>
        </div>
        <div class="nav">
          <button class="btn" data-go="cover">☰ Trang bìa</button>
          <button class="btn primary" id="next">${state.idx + 1 < iss.articles.length ? "Đọc xong, bài tiếp →" : "Đọc xong 🎉"}</button>
        </div>
      </article>`, { back: "cover" });
  }

  function viewDone() {
    const iss = state.issue;
    const ans = Object.entries(state.answers[iss.date] || {}).filter(([, x]) => x.reader === state.reader && x.text);
    return shell(`
      <section class="done">
        <div class="big">🌟</div>
        <h1>Hôm nay bạn đọc hết ${iss.articles.length} bài!</h1>
        <p>Hẹn gặp lại ngày mai với số báo mới nhé.</p>
        ${ans.length ? `<div style="text-align:left;max-width:600px;margin:0 auto 20px">
          <h4>Bạn đã viết:</h4>${ans.map(([id, x]) => { const a = iss.articles.find(a => a.id === id); return a ? `<div class="box"><b>${esc(version(a).title)}</b><p style="margin:6px 0 0">${esc(x.text)}</p></div>` : ""; }).join("")}</div>` : ""}
        <button class="btn" data-go="cover">Về trang bìa</button>
      </section>`, { hideReader: false });
  }

  function viewParent() {
    if (!state.parentUnlocked) {
      return shell(`
        <section class="done"><div class="big">🔒</div><h1>Góc cha mẹ</h1><p>Nhập mã 4 số</p>
          <div class="pin">${[0, 1, 2, 3].map(i => `<input inputmode="numeric" maxlength="1" pattern="[0-9]" data-pin="${i}" aria-label="số ${i + 1}">`).join("")}</div>
          <div class="muted" id="pin-msg">Mã mặc định 1234, đổi được ở trong.</div>
          <div style="margin-top:14px"><button class="btn" data-go="cover">Quay lại</button></div>
        </section>`, { hideReader: true });
    }
    const iss = state.issue;
    const rows = Object.entries(state.answers).flatMap(([date, m]) => Object.entries(m).map(([id, x]) => ({ date, id, ...x }))).sort((a, b) => b.at.localeCompare(a.at));
    const titleOf = (date, id) => (date === iss.date ? iss.articles.find(a => a.id === id) : null);
    return shell(`
      <section class="parent">
        <h2>Số báo hôm nay (${fmtDate(iss.date)}) — nguồn để đối chiếu</h2>
        <p class="muted">Trẻ không thấy phần này. Link chỉ dành cho bố mẹ kiểm tra bài gốc.</p>
        <table><tr><th>Mục</th><th>Bài</th><th>Nguồn</th><th>Điểm</th></tr>
          ${iss.articles.map(a => `<tr><td>${a.emoji} ${esc(a.section_name)}</td><td>${esc(version(a).title)}</td>
            <td><a href="${esc(a.source_url)}" target="_blank" rel="noopener">${esc(a.source_name)}</a></td><td>${a.score ?? ""}</td></tr>`).join("")}
        </table>
        <h2>Câu trả lời của các con (${rows.length})</h2>
        ${rows.length ? `<table><tr><th>Ngày</th><th>Ai</th><th>Bài</th><th>Trả lời</th></tr>
          ${rows.slice(0, 60).map(r => { const a = titleOf(r.date, r.id); return `<tr><td>${esc(r.date)}</td><td>${r.reader === "be-nho" ? "Bé 7" : "Bé 11"}</td><td>${a ? esc(version(a).title) : "<span class=muted>số cũ</span>"}</td><td>${esc(r.text)}</td></tr>`; }).join("")}</table>`
          : `<p class="muted">Chưa có câu trả lời nào.</p>`}
        <h2>Các số báo trước</h2>
        <div class="row" id="history"><span class="muted">Đang tải…</span></div>
        <h2>Cài đặt</h2>
        <div class="row">
          <button class="btn small" id="change-pin">Đổi mã PIN</button>
          <button class="btn small" id="clear-read">Đánh dấu chưa đọc hôm nay</button>
          <button class="btn small" id="clear-all">Xóa toàn bộ dữ liệu trên máy này</button>
        </div>
        <p class="muted" style="margin-top:14px">Sinh lúc ${esc(iss.generated_at || "")}. Sửa tiêu chí lọc, nguồn, độ tuổi trong <code>config/newspaper.yaml</code> trên máy tính.</p>
        <div style="margin-top:18px"><button class="btn" data-go="cover">← Về báo</button></div>
      </section>`, { hideReader: true });
  }

  // ---------- Render + sự kiện ----------
  function render() {
    tts.stop(document.getElementById("tts"));
    document.documentElement.dataset.reader = state.reader || "";
    let html;
    if (!state.issue) html = shell(`<div class="empty"><div style="font-size:3rem">📭</div><h2>Chưa có số báo</h2><p>Máy tính chưa chạy số báo hôm nay, hoặc chưa có mạng lần đầu.</p><button class="btn" id="retry">Thử lại</button></div>`, { hideReader: true });
    else if (state.view === "parent") html = viewParent();
    else if (!state.reader || state.view === "pick") html = viewPick();
    else if (state.view === "article") html = viewArticle();
    else if (state.view === "done") html = viewDone();
    else html = viewCover();
    $app.innerHTML = html;
    window.scrollTo({ top: 0 });
    bind();
  }

  function bind() {
    $app.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => {
      const v = b.dataset.go;
      if (v === "parent") state.parentUnlocked = false;
      state.view = v; render();
    }));
    $app.querySelectorAll("[data-reader]").forEach(b => b.addEventListener("click", () => {
      state.reader = b.dataset.reader; LS.set("reader", state.reader); state.view = "cover"; render();
    }));
    $app.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => {
      state.idx = +b.dataset.open; state.view = "article"; render();
    }));
    document.getElementById("retry")?.addEventListener("click", boot);

    // Bài đọc
    const a = state.issue?.articles?.[state.idx];
    const ttsBtn = document.getElementById("tts");
    if (ttsBtn && a) ttsBtn.addEventListener("click", () => {
      const v = version(a);
      tts.speak(`${v.title}. ${v.lead}. ${v.body}`, ttsBtn);
    });
    $app.querySelectorAll(".chip").forEach(c => c.addEventListener("click", () => c.classList.toggle("open")));
    const ta = document.getElementById("answer");
    if (ta && a) {
      let t;
      ta.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(() => {
          state.answers[state.issue.date] = state.answers[state.issue.date] || {};
          state.answers[state.issue.date][a.id] = { reader: state.reader, text: ta.value.trim(), at: new Date().toISOString() };
          LS.set("answers", state.answers);
          document.getElementById("saved").textContent = ta.value.trim() ? "Đã lưu câu trả lời của bạn." : "";
        }, 500);
      });
    }
    document.getElementById("next")?.addEventListener("click", () => {
      markRead(a);
      const next = state.issue.articles.findIndex((x, i) => i > state.idx && !isRead(x));
      const any = state.issue.articles.findIndex(x => !isRead(x));
      if (next >= 0) { state.idx = next; state.view = "article"; }
      else if (any >= 0) { state.idx = any; state.view = "article"; }
      else state.view = "done";
      render();
    });

    // PIN
    const pins = [...$app.querySelectorAll("[data-pin]")];
    if (pins.length) {
      pins[0].focus();
      const checkPin = () => {
        const code = pins.map(p => p.value).join("");
        if (code.length !== 4) return;
        if (code === state.pin) { state.parentUnlocked = true; render(); loadHistory(); }
        else { document.getElementById("pin-msg").textContent = "Sai mã, thử lại."; pins.forEach(p => p.value = ""); pins[0].focus(); }
      };
      pins.forEach((inp, i) => {
        inp.addEventListener("input", () => {
          // gõ nhanh hoặc dán nhiều số: rải từng số sang các ô tiếp theo
          const digits = inp.value.replace(/\D/g, "");
          inp.value = digits.slice(0, 1);
          digits.slice(1).split("").forEach((d, k) => { if (pins[i + 1 + k]) pins[i + 1 + k].value = d; });
          const nextIdx = Math.min(3, i + Math.max(1, digits.length));
          if (digits && nextIdx > i) pins[nextIdx].focus();
          checkPin();
        });
        inp.addEventListener("keydown", e => {
          if (e.key === "Backspace" && !inp.value && i > 0) { pins[i - 1].value = ""; pins[i - 1].focus(); e.preventDefault(); }
        });
      });
    }
    if (state.parentUnlocked && state.view === "parent") loadHistory();
    document.getElementById("change-pin")?.addEventListener("click", () => {
      const p = prompt("Mã PIN mới (4 số):", "");
      if (p && /^\d{4}$/.test(p)) { state.pin = p; LS.set("pin", p); alert("Đã đổi mã."); }
    });
    document.getElementById("clear-read")?.addEventListener("click", () => { delete state.read[state.issue.date]; LS.set("read", state.read); alert("Đã đánh dấu chưa đọc."); });
    document.getElementById("clear-all")?.addEventListener("click", () => {
      if (confirm("Xóa toàn bộ câu trả lời, tiến độ và cài đặt trên máy này?")) { ["reader", "read", "answers", "pin"].forEach(LS.del); location.reload(); }
    });
  }

  async function loadHistory() {
    const el = document.getElementById("history"); if (!el) return;
    try {
      const idx = await (await fetch("data/index.json", { cache: "no-cache" })).json();
      const dates = (idx.issues || []).filter(d => d !== state.issue.date).slice(0, 14);
      el.innerHTML = dates.length ? dates.map(d => `<button class="btn small" data-date="${d}">${d}</button>`).join("") : '<span class="muted">Chưa có số nào trước.</span>';
      el.querySelectorAll("[data-date]").forEach(b => b.addEventListener("click", async () => {
        const j = await loadIssue(b.dataset.date); if (j) { state.issue = j; state.view = "cover"; render(); }
      }));
    } catch { el.innerHTML = '<span class="muted">Không tải được danh mục.</span>'; }
  }

  async function boot() {
    state.issue = await loadIssue();
    if (state.issue && !state.issue.articles?.length) state.issue = null;
    render();
  }
  if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = () => {};
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  boot();
})();
