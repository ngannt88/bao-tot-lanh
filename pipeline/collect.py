"""TẦNG 1 — Thu thập RSS từ nguồn đã duyệt (whitelist). Chỉ lấy đúng chuyên mục sạch."""
from __future__ import annotations
import time, concurrent.futures as cf
import feedparser, requests
from common import (setup_logging, strip_html, article_id, norm, read_json, write_json,
                    STATE, RAW, today_str)

log = setup_logging()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BaoTotLanh/0.1 (+family reader)"}
MAX_AGE_H = 36          # chỉ lấy bài trong 1,5 ngày
MAX_PER_FEED = 30


def _fetch(src: dict) -> list[dict]:
    try:
        r = requests.get(src["url"], headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.warning("Feed lỗi %s: %s", src["id"], str(e)[:100])
        return []
    fp = feedparser.parse(r.content)
    out = []
    now = time.time()
    for e in fp.entries[:MAX_PER_FEED]:
        link = (e.get("link") or "").strip()
        title = strip_html(e.get("title"))
        if not link or not title:
            continue
        ts = e.get("published_parsed") or e.get("updated_parsed")
        age_h = (now - time.mktime(ts)) / 3600 if ts else None
        if age_h is not None and age_h > src.get("max_age_h", MAX_AGE_H):
            continue
        img = None
        for m in e.get("media_content", []) or []:
            if m.get("url"):
                img = m["url"]; break
        if not img:
            for enc in e.get("enclosures", []) or []:
                if str(enc.get("type", "")).startswith("image") and enc.get("href"):
                    img = enc["href"]; break
        out.append({
            "id": article_id(link),
            "url": link,
            "title": title,
            "summary": strip_html(e.get("summary") or e.get("description"))[:600],
            "published": time.strftime("%Y-%m-%dT%H:%M:%S+07:00", time.localtime(time.mktime(ts))) if ts else None,
            "age_h": round(age_h, 1) if age_h is not None else None,
            "source": src["id"],
            "source_name": src.get("name", src["id"]),
            "lang": src.get("lang", "vi"),
            "hint_section": src.get("section"),
            "image_src": img,
        })
    log.info("Feed %-28s %3d bài", src["id"], len(out))
    return out


def collect(sources: list[dict]) -> list[dict]:
    active = [s for s in sources if s.get("enabled", True)]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        lists = list(ex.map(_fetch, active))
    items = [a for lst in lists for a in lst]

    # Khử trùng lặp theo url và theo tiêu đề gần giống (cùng sự kiện nhiều báo đăng)
    state = read_json(STATE, {"seen": {}, "titles": {}})
    seen_urls = state["seen"]
    uniq, seen_titles = [], set(state.get("titles", {}).keys())   # tiêu đề đã thấy 3 ngày gần đây
    dropped_seen = dropped_dup = 0
    for a in items:
        if a["id"] in seen_urls:
            dropped_seen += 1
            continue
        key = norm(a["title"])[:70]
        if key in seen_titles:
            dropped_dup += 1
            continue
        seen_titles.add(key)
        uniq.append(a)
    log.info("Thu được %d bài, bỏ %d đã thấy, %d trùng tiêu đề → còn %d",
             len(items), dropped_seen, dropped_dup, len(uniq))
    write_json(RAW / f"{today_str()}.json", uniq)
    return uniq


def mark_seen(articles: list[dict]) -> None:
    state = read_json(STATE, {"seen": {}, "titles": {}})
    day = today_str()
    titles = state.setdefault("titles", {})
    for a in articles:
        state["seen"][a["id"]] = day
        titles[norm(a["title"])[:70]] = day
    keep_t = sorted(set(titles.values()))[-3:]
    state["titles"] = {k: v for k, v in titles.items() if v in keep_t}
    # Giữ 30 ngày để file không phình
    keep = sorted(set(state["seen"].values()))[-30:]
    state["seen"] = {k: v for k, v in state["seen"].items() if v in keep}
    write_json(STATE, state)
