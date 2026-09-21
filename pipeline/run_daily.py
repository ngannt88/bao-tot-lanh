"""Chạy toàn bộ 4 tầng cho một ngày.

  python pipeline/run_daily.py            # chạy thật, xuất số báo hôm nay
  python pipeline/run_daily.py --dry-run  # chỉ tầng 1–3, in danh sách, không viết lại
  python pipeline/run_daily.py --no-ai    # chỉ tầng 1–2, xem lọc luật hoạt động thế nào
  python pipeline/run_daily.py --check    # kiểm tra đăng nhập CLI
"""
from __future__ import annotations
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from common import load_config, setup_logging, today_str, write_json, DATA
from collect import collect, mark_seen
from rules import apply_rules
from score import score_articles
from build_issue import select_candidates, build

log = setup_logging()


def print_table(rows, cols, limit=60):
    for r in rows[:limit]:
        print("  " + " | ".join(str(r.get(c, ""))[:w] for c, w in cols))
    if len(rows) > limit:
        print(f"  ... và {len(rows) - limit} bài nữa")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="tầng 1–3, không viết lại, không xuất")
    ap.add_argument("--no-ai", action="store_true", help="chỉ tầng 1–2")
    ap.add_argument("--check", action="store_true", help="kiểm tra đăng nhập CLI rồi thoát")
    ap.add_argument("--date", default=None, help="ghi số báo vào ngày này (YYYY-MM-DD)")
    ap.add_argument("--no-mark", action="store_true", help="không ghi nhớ url đã thấy (để chạy thử lặp lại)")
    args = ap.parse_args()

    cfg = load_config()
    if args.check:
        from ai import check_login
        ok, msg = check_login()
        print(("OK " if ok else "LỖI ") + msg)
        sys.exit(0 if ok else 1)

    t0 = time.time()
    day = args.date or today_str()
    log.info("=== %s — bắt đầu số báo %s ===", cfg["paper"]["name"], day)

    # Tầng 1
    raw = collect(cfg["sources"])
    # Tầng 2
    passed, blocked = apply_rules(raw, cfg)
    if args.no_ai:
        print("\nBỊ CHẶN BỞI LUẬT:")
        print_table(blocked, [("title", 70), ("reject_reasons", 40)])
        print("\nQUA TẦNG 2 (sẽ đưa AI chấm):")
        print_table(passed, [("source", 22), ("title", 80)])
        return
    # Tầng 3
    scored = score_articles(passed, cfg)
    auto, review, rejected_score = select_candidates(scored, cfg)
    write_json(DATA / "raw" / f"{day}-scored.json", scored)
    print(f"\nTỰ ĐỘNG LÊN BÁO (≥{cfg['scoring']['threshold_auto']}): {len(auto)}")
    print_table(auto, [("score", 2), ("section", 20), ("title", 70), ("reason", 40)])
    print(f"\nHÀNG CHỜ DUYỆT: {len(review)}")
    print_table(review, [("score", 2), ("section", 20), ("title", 70), ("reason", 40)], 25)
    print(f"\nLOẠI BỞI AI: {len(rejected_score)}")
    print_table(rejected_score, [("score", 2), ("title", 70), ("reason", 40)], 25)
    if args.dry_run:
        build(auto, review, blocked, rejected_score, cfg, day, dry_run=True)
        log.info("Dry-run xong sau %.0fs", time.time() - t0)
        return
    # Tầng 4 + xuất
    issue = build(auto, review, blocked, rejected_score, cfg, day)
    if issue and not args.no_mark:
        mark_seen(raw)
    log.info("Xong sau %.0fs", time.time() - t0)


if __name__ == "__main__":
    main()
