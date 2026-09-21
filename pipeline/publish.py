"""Xuất bản số báo từ các ứng viên cha mẹ đã chọn: chép ảnh, ghi JSON, đẩy lên GitHub."""
from __future__ import annotations
import shutil, subprocess
from common import setup_logging, write_json, read_json, ROOT, SITE_DATA, ISSUES, now_vn, slug
from candidates import load as load_candidates, CAND_IMG

log = setup_logging()
IMG_PUB = SITE_DATA / "img"


def build_issue(day: str, ids: list[str], cfg: dict) -> dict:
    data = load_candidates(day)
    if not data:
        raise FileNotFoundError(f"Chưa có ứng viên ngày {day}")
    by_id = {c["id"]: c for c in data["candidates"]}
    secs = {s["id"]: s for s in cfg["sections"]}
    items = []
    for order, cid in enumerate(ids, 1):
        c = by_id.get(cid)
        if not c:
            log.warning("Bỏ id không có trong ứng viên: %s", cid)
            continue
        # chép ảnh sang docs/data/img/<day>/
        dest_dir = IMG_PUB / day
        dest_dir.mkdir(parents=True, exist_ok=True)
        images = []
        for im in c.get("images", []):
            src = CAND_IMG / day / im["file"]
            if src.exists():
                shutil.copy2(src, dest_dir / im["file"])
                images.append({"src": f"img/{day}/{im['file']}", "caption": im.get("caption", ""), "w": im["w"], "h": im["h"]})
            else:
                images.append(None)
        # đánh lại chỉ số ảnh sau khi bỏ ảnh thiếu
        remap, clean = {}, []
        for i, im in enumerate(images):
            if im:
                remap[i] = len(clean); clean.append(im)
        blocks = []
        for b in c.get("blocks", []):
            if b["t"] == "img":
                if b["i"] in remap:
                    blocks.append({"t": "img", "i": remap[b["i"]]})
            else:
                blocks.append(b)
        sid = c.get("section") or c.get("hint_section")
        s = secs.get(sid, {"name": "Khác", "emoji": "📰"})
        items.append({
            "id": c["id"], "order": order, "slug": slug(c["title"]),
            "section": sid, "section_name": s["name"], "emoji": s["emoji"],
            "title": c["title"], "sapo": c.get("sapo", ""), "author": c.get("author", ""),
            "source_name": c["source_name"], "source_url": c["url"], "published": c.get("published"),
            "lang": c.get("lang", "vi"), "score": c.get("score"), "words": c.get("words"),
            "images": clean, "lead": 0 if clean else None, "blocks": blocks,
        })
    issue = {
        "date": day, "paper": cfg["paper"]["name"], "tagline": cfg["paper"]["tagline"],
        "generated_at": now_vn().isoformat(timespec="seconds"),
        "sections": [{"id": s["id"], "name": s["name"], "emoji": s["emoji"]} for s in cfg["sections"]],
        "articles": items,
    }
    write_json(ISSUES / f"{day}.json", issue)
    write_json(SITE_DATA / "latest.json", issue)
    index = read_json(SITE_DATA / "index.json", {"issues": []})
    index["issues"] = sorted({*index["issues"], day}, reverse=True)[:90]
    write_json(SITE_DATA / "index.json", index)
    log.info("Đã ghi số báo %s: %d bài", day, len(items))
    return issue


def git_push(day: str) -> tuple[bool, str]:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not (ROOT / ".git").exists():
        return False, "chưa có kho git"
    run("add", "docs/data")
    st = run("status", "--porcelain", "docs/data")
    if not st.stdout.strip():
        return True, "không có gì mới để đẩy"
    c = run("commit", "-q", "-m", f"Số báo {day}")
    if c.returncode != 0:
        return False, "commit lỗi: " + (c.stderr or c.stdout)[-300:]
    p = run("push", "-q")
    if p.returncode != 0:
        return False, "push lỗi: " + (p.stderr or p.stdout)[-300:]
    return True, "đã đẩy lên GitHub"


def publish(day: str, ids: list[str], cfg: dict, push: bool = True) -> dict:
    issue = build_issue(day, ids, cfg)
    ok, msg = (True, "không đẩy") if not push else git_push(day)
    return {"ok": ok, "message": msg, "count": len(issue["articles"]), "date": day}


if __name__ == "__main__":
    import argparse, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from common import load_config, today_str
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--date", default=today_str())
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    print(publish(a.date, a.ids, load_config(), push=not a.no_push))
