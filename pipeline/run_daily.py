"""Chạy 3 tầng lọc rồi tách nguyên văn các ứng viên cho cha mẹ duyệt.

  python pipeline/run_daily.py            # lấy tin, lọc, chấm, tách → data/candidates/YYYY-MM-DD.json
  python pipeline/run_daily.py --no-ai    # bỏ tầng AI (khi chưa đăng nhập CLI), chọn xoay vòng theo mục
  python pipeline/run_daily.py --force    # chạy lại dù hôm nay đã có ứng viên
  python pipeline/run_daily.py --check    # kiểm tra đăng nhập CLI
Sau đó mở http://localhost:8765/duyet.html (review_server.py) để chọn bài và xuất bản.
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from common import load_config, setup_logging, today_str
from collect import collect, mark_seen
from rules import apply_rules
from candidates import select, extract_all, save, load, CAND_DIR

log = setup_logging()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-mark", action="store_true", help="không ghi nhớ url đã thấy")
    args = ap.parse_args()
    cfg = load_config()

    if args.check:
        from ai import check_login
        ok, msg = check_login()
        print(("OK " if ok else "LỖI ") + msg)
        sys.exit(0 if ok else 1)

    day = args.date or today_str()
    if not args.force and load(day):
        log.info("Ứng viên ngày %s đã có (%s). Dùng --force để chạy lại.", day, CAND_DIR / f"{day}.json")
        return

    t0 = time.time()
    log.info("=== %s — lấy ứng viên ngày %s ===", cfg["paper"]["name"], day)
    raw = collect(cfg["sources"])
    passed, blocked = apply_rules(raw, cfg)

    scored, has_scores, rejected_score = passed, False, []
    if not args.no_ai:
        try:
            from score import score_articles
            from ai import check_login
            ok, msg = check_login()
            if not ok:
                log.warning("AI chưa sẵn sàng (%s) → chọn ứng viên không có điểm AI. Chạy 'claude login' để bật.", msg)
            else:
                scored = score_articles(passed, cfg)
                has_scores = any(a.get("score") is not None for a in scored)
                min_score = cfg.get("review", {}).get("min_score_candidate", 6)
                rejected_score = [a for a in scored if a.get("score") is not None and a["score"] < min_score]
        except Exception as e:
            log.error("Tầng AI lỗi: %s → tiếp tục không có điểm AI", e)

    chosen = select(scored, cfg, has_scores)
    ok, bad = extract_all(chosen, day)
    unsafe = []
    if has_scores and ok:
        # VÒNG 2: đọc nội dung thật của ứng viên, chặn bài không an toàn trước khi lên trang duyệt / tự xuất bản
        from score import verify_candidates
        ok = verify_candidates(ok, cfg)
        unsafe = [c for c in ok if c.get("safe") is False]
        ok = [c for c in ok if c.get("safe") is not False]
        ok.sort(key=lambda c: -(c.get("score") or 0))
        for c in unsafe:
            c["extract_error"] = "AI vòng 2: không an toàn — " + (c.get("reason2") or "")
        bad = bad + unsafe
    payload = save(day, cfg, ok, has_scores, blocked, rejected_score, bad)
    if not args.no_mark:
        mark_seen(raw)

    print(f"\nỨNG VIÊN NGÀY {day}: {len(ok)} bài" + ("" if has_scores else "  (chưa có điểm AI)"))
    for a in ok:
        sc = f"{a['score']:>2}" if a.get("score") is not None else " -"
        two = f" v1={a['score1']} v2={a['score2']}" if a.get("verified") else ""
        print(f"  [{sc}] {a.get('section') or a.get('hint_section') or '':20} {a['source_name']:12} {a['title'][:60]}  ({len(a['images'])} ảnh, {a['words']} chữ){two} {a.get('reason2','')[:30]}")
    if unsafe:
        print(f"\nVÒNG 2 CHẶN {len(unsafe)} bài:")
        for c in unsafe: print(f"  ✗ {c['title'][:70]} — {c.get('reason2','')}")
    print(f"\nMở http://localhost:8765/duyet.html để chọn và xuất bản.  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
