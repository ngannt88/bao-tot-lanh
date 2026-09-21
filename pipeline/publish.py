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
    """Hai việc:
    1. main: commit JSON số báo (nhỏ, giữ lịch sử). Ảnh KHÔNG vào main (.gitignore) để kho không phình.
    2. gh-pages: nhánh web, dựng lại từ toàn bộ thư mục docs/ (kể cả ảnh) thành MỘT commit không cha,
       đẩy ghi đè. Không có lịch sử → kho không lớn theo ngày. GitHub Pages phục vụ nhánh này."""
    import os
    def run(*args, env=None):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
    if not (ROOT / ".git").exists():
        return False, "chưa có kho git"
    msgs = []
    # 1) main
    run("add", "docs/data")
    if run("status", "--porcelain", "docs/data").stdout.strip():
        c = run("commit", "-q", "-m", f"Số báo {day}")
        if c.returncode != 0:
            return False, "commit lỗi: " + (c.stderr or c.stdout)[-300:]
        p = run("push", "-q")
        if p.returncode != 0:
            return False, "push main lỗi: " + (p.stderr or p.stdout)[-300:]
        msgs.append("main")
    # 2) gh-pages = snapshot docs/ (dùng index tạm để lấy cả file bị ignore như ảnh)
    tmp_index = ROOT / ".git" / "tmp-pages-index"
    env = dict(os.environ, GIT_INDEX_FILE=str(tmp_index))
    try:
        if tmp_index.exists():
            tmp_index.unlink()
        a = run("add", "-f", "docs", env=env)
        if a.returncode != 0:
            return False, "gh-pages add lỗi: " + (a.stderr or a.stdout)[-300:]
        t = run("write-tree", "--prefix=docs/", env=env)
        if t.returncode != 0:
            return False, "gh-pages write-tree lỗi: " + (t.stderr or t.stdout)[-300:]
        tree = t.stdout.strip()
        cm = run("commit-tree", tree, "-m", f"Trang web {day}")
        if cm.returncode != 0:
            return False, "gh-pages commit-tree lỗi: " + (cm.stderr or cm.stdout)[-300:]
        run("update-ref", "refs/heads/gh-pages", cm.stdout.strip())
        p = run("push", "-q", "-f", "origin", "gh-pages")
        if p.returncode != 0:
            return False, "push gh-pages lỗi: " + (p.stderr or p.stdout)[-300:]
        msgs.append("gh-pages")
    finally:
        if tmp_index.exists():
            tmp_index.unlink()
    return True, "đã đẩy lên GitHub (" + ", ".join(msgs) + ")"


def publish(day: str, ids: list[str], cfg: dict, push: bool = True) -> dict:
    issue = build_issue(day, ids, cfg)
    ok, msg = (True, "không đẩy") if not push else git_push(day)
    return {"ok": ok, "message": msg, "count": len(issue["articles"]), "date": day}


def auto_pick(day: str, cfg: dict) -> list[str]:
    """Chọn tự động: bài điểm AI ≥ min_score, cân bằng chuyên mục, đủ articles_per_issue.
    Không có điểm AI → trả rỗng (không tự xuất bản khi chưa có AI)."""
    data = load_candidates(day)
    if not data or not data.get("ai_scored"):
        return []
    ap_cfg = cfg.get("review", {}).get("auto_publish", {})
    min_score = ap_cfg.get("min_score", 8)
    n = cfg["paper"]["articles_per_issue"]
    secs = {s["id"]: s for s in cfg["sections"]}
    pool = sorted([c for c in data["candidates"] if (c.get("score") or 0) >= min_score],
                  key=lambda c: (-c["score"], c.get("age_h") or 99))
    chosen, count = [], {}
    for sid, s in secs.items():                      # mỗi mục bắt buộc 1 bài trước
        if s.get("required"):
            for c in pool:
                if c not in chosen and c.get("section") == sid:
                    chosen.append(c); count[sid] = 1; break
    for c in pool:
        if len(chosen) >= n:
            break
        sid = c.get("section")
        if c in chosen or count.get(sid, 0) >= secs.get(sid, {}).get("max_per_issue", 2):
            continue
        chosen.append(c); count[sid] = count.get(sid, 0) + 1
    return [c["id"] for c in chosen]


if __name__ == "__main__":
    import argparse, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from common import load_config, today_str
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--date", default=today_str())
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--auto", action="store_true", help="tự chọn bài điểm cao nếu hôm nay chưa xuất bản")
    a = ap.parse_args()
    cfg = load_config()
    if a.auto:
        if not cfg.get("review", {}).get("auto_publish", {}).get("enabled"):
            print("Tự xuất bản đang tắt trong config."); sys.exit(0)
        if (ISSUES / f"{a.date}.json").exists():
            print(f"Ngày {a.date} đã có số báo (cha mẹ đã duyệt), không làm gì."); sys.exit(0)
        ids = auto_pick(a.date, cfg)
        if not ids:
            print("Không tự xuất bản: chưa có ứng viên có điểm AI đủ cao."); sys.exit(2)
        res = publish(a.date, ids, cfg, push=not a.no_push)
        print("TỰ XUẤT BẢN:", res)
        try:
            import subprocess
            subprocess.run(["powershell", "-NoProfile", "-Command",
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
                f"$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                f"$t=$x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('Báo Tốt Lành: đã tự xuất bản {res['count']} bài')) | Out-Null; "
                f"$t.Item(1).AppendChild($x.CreateTextNode('Bạn chưa duyệt nên hệ thống chọn bài điểm cao. Mở trang duyệt để chỉnh nếu cần.')) | Out-Null; "
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Báo Tốt Lành').Show([Windows.UI.Notifications.ToastNotification]::new($x))"],
                timeout=20)
        except Exception:
            pass
        sys.exit(0 if res["ok"] else 1)
    if not a.ids:
        ap.error("cần danh sách id hoặc --auto")
    print(publish(a.date, a.ids, cfg, push=not a.no_push))
