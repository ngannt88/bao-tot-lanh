"""Kiểm tra sức khỏe: mỗi nguồn còn sống không, bộ tách còn đúng không (1 bài mới nhất mỗi báo).
Chạy tay hoặc hàng tuần:  python pipeline/selfcheck.py
Báo đổi giao diện → bài mất ảnh/mất đoạn sẽ lộ ra ở đây trước khi con thấy."""
from __future__ import annotations
import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import feedparser, requests
from common import load_config, setup_logging, write_json, DATA, today_str, http_get
from collect import HEADERS
from extract import extract_article

log = setup_logging()
MIN_PARAS, MIN_IMAGES = 4, 1


def main():
    cfg = load_config()
    tmp = Path(tempfile.mkdtemp(prefix="btl-selfcheck-"))
    rows, bad = [], 0
    seen_domain = set()
    for src in cfg["sources"]:
        if not src.get("enabled", True):
            continue
        row = {"id": src["id"], "name": src["name"], "feed_ok": False, "items": 0, "extract_ok": None}
        try:
            r = http_get(src["url"], HEADERS, 20)
            fp = feedparser.parse(r.content)
            row["items"] = len(fp.entries)
            row["feed_ok"] = r.status_code == 200 and len(fp.entries) > 0
        except Exception as e:
            row["error"] = str(e)[:80]
        domain = src["url"].split("/")[2]
        if row["feed_ok"] and domain not in seen_domain:
            seen_domain.add(domain)
            e = fp.entries[0]
            a = {"id": "chk", "url": e.link, "title": e.get("title", ""), "summary": "", "source": src["id"],
                 "source_name": src["name"], "lang": src.get("lang", "vi")}
            t0 = time.time()
            x = extract_article(a, tmp)
            paras = sum(1 for b in x.get("blocks", []) if b["t"] == "p")
            row.update(extract_ok=bool(x.get("extracted_ok")) and paras >= MIN_PARAS and len(x.get("images", [])) >= MIN_IMAGES,
                       paras=paras, images=len(x.get("images", [])), words=x.get("words", 0),
                       author=bool(x.get("author")), sapo=bool(x.get("sapo")), secs=round(time.time() - t0, 1),
                       sample=e.link, extract_error=x.get("extract_error"))
        status = "OK " if row["feed_ok"] and row["extract_ok"] in (True, None) else "LỖI"
        if status == "LỖI":
            bad += 1
        extra = ""
        if row["extract_ok"] is not None:
            extra = f" | tách: {row['paras']} đoạn, {row['images']} ảnh, {row['words']} chữ, tác giả {'✓' if row['author'] else '✗'}, sapo {'✓' if row['sapo'] else '✗'}"
            if row.get("extract_error"):
                extra += f" ({row['extract_error']})"
        print(f"{status} {src['id']:24} feed {row['items']:3} bài{extra}")
        rows.append(row)
    write_json(DATA / "logs" / f"selfcheck-{today_str()}.json", rows)
    print(f"\n{len(rows) - bad}/{len(rows)} nguồn ổn." + (f"  {bad} nguồn cần xem lại." if bad else ""))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
