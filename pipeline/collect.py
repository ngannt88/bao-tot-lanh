"""TẦNG 1 — Thu thập RSS từ nguồn đã duyệt (whitelist). Chỉ lấy đúng chuyên mục sạch."""
from __future__ import annotations
import time, concurrent.futures as cf
import feedparser, requests
from common import (setup_logging, strip_html, article_id, norm, read_json, write_json,
                    STATE, RAW, today_str, http_get)

log = setup_logging()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BaoTotLanh/0.1 (+family reader)"}
MAX_AGE_H = 36          # chỉ lấy bài trong 1,5 ngày
MAX_PER_FEED = 30


# Hậu tố cấp hai của tên miền quốc gia: "dantri.com.vn" phải giữ 3 nhãn, "ieee.org" giữ 2.
_SLD = {"com", "net", "org", "edu", "gov", "co", "ac"}


def _domain(host: str) -> str:
    parts = (host or "").lower().lstrip(".").split(".")
    if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in _SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _same_site(link: str, feed_url: str, allow: list[str]) -> bool:
    """Bài trong RSS phải thuộc đúng tên miền của nguồn.

    Vì sao bắt buộc: cả hệ thống dựa trên whitelist nguồn, nhưng RSS của một số báo có
    chèn bài tài trợ trỏ sang tên miền khác. Đã gặp thật: feed IEEE Spectrum trả bài
    quảng cáo ở content.knowledgehub.wiley.com và bài đó tách nội dung "thành công",
    tức là suýt lên báo cho con đọc như một bài công nghệ bình thường.
    """
    from urllib.parse import urlparse
    host = urlparse(link).netloc.lower()
    if not host:
        return False
    d = _domain(host)
    return d == _domain(urlparse(feed_url).netloc) or d in {_domain(h) for h in allow}


def _fetch(src: dict) -> list[dict]:
    try:
        r = http_get(src["url"], HEADERS, 20)
        r.raise_for_status()
    except Exception as e:
        log.warning("Feed lỗi %s: %s", src["id"], str(e)[:100])
        return []
    fp = feedparser.parse(r.content)
    out, off_site = [], []
    now = time.time()
    for e in fp.entries[:MAX_PER_FEED]:
        link = (e.get("link") or "").strip()
        title = strip_html(e.get("title"))
        if not link or not title:
            continue
        if not _same_site(link, src["url"], src.get("allow_hosts") or []):
            off_site.append(link)
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
    log.info("Feed %-28s %3d bài%s", src["id"], len(out),
             f" (bỏ {len(off_site)} bài ngoài tên miền)" if off_site else "")
    if off_site:
        log.debug("Ngoài tên miền (%s): %s", src["id"], ", ".join(off_site[:3]))
    return out


def _fetch_html_listing(src: dict) -> list[dict]:
    """Nguồn KHÔNG có RSS: lấy link bài từ trang chuyên mục theo mẫu regex (type: html)."""
    import re
    from urllib.parse import urljoin, urlparse
    from bs4 import BeautifulSoup
    try:
        r = http_get(src["url"], HEADERS, src.get("timeout", 40))
        r.raise_for_status()
    except Exception as e:
        log.warning("Trang chuyên mục lỗi %s: %s", src["id"], str(e)[:100])
        return []
    soup = BeautifulSoup(r.content, "lxml")
    pat = re.compile(src["link_pattern"])
    host = urlparse(r.url).netloc
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        link = urljoin(r.url, a["href"]).split("#")[0]
        if urlparse(link).netloc != host or not pat.search(link) or link in seen:
            continue
        title = strip_html(a.get("title") or a.get_text(" ", strip=True))
        if not title or len(title) < 15:            # bỏ link ảnh/"Xem thêm" không có tiêu đề
            img = a.find("img")
            title = strip_html(img.get("alt")) if img is not None and img.get("alt") else ""
            if len(title) < 15:
                continue
        seen.add(link)
        out.append({
            "id": article_id(link), "url": link, "title": title, "summary": "",
            "published": None, "age_h": None,                 # trang chuyên mục không có ngày; state 'seen' lo việc lặp
            "source": src["id"], "source_name": src.get("name", src["id"]), "lang": src.get("lang", "vi"),
            "hint_section": src.get("section"), "image_src": None,
        })
        if len(out) >= src.get("max_items", 20):
            break
    log.info("Trang %-27s %3d bài", src["id"], len(out))
    return out


def collect(sources: list[dict], ignore_today: bool = False) -> list[dict]:
    """ignore_today=True: bỏ qua bộ nhớ "đã thấy" của CHÍNH HÔM NAY, để chạy lại trong ngày
    vẫn ra đủ bài (các ngày trước vẫn được nhớ, không lấy lại bài cũ)."""
    active = [s for s in sources if s.get("enabled", True)]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        lists = list(ex.map(lambda s: _fetch_html_listing(s) if s.get("type") == "html" else _fetch(s), active))
    items = [a for lst in lists for a in lst]

    # Khử trùng lặp theo url và theo tiêu đề gần giống (cùng sự kiện nhiều báo đăng)
    state = read_json(STATE, {"seen": {}, "titles": {}})
    today = today_str()
    seen_urls = state["seen"]
    seen_titles_map = state.get("titles", {})
    if ignore_today:
        seen_urls = {k: v for k, v in seen_urls.items() if v != today}
        seen_titles_map = {k: v for k, v in seen_titles_map.items() if v != today}
    uniq, seen_titles = [], set(seen_titles_map.keys())   # tiêu đề đã thấy 3 ngày gần đây
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
