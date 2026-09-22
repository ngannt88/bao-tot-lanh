"""Dọn dẹp dữ liệu cũ. Chạy tự động sau mỗi lần lấy tin và mỗi lần xuất bản.

Vì sao cần: mỗi ngày báo tải về khoảng 80 MB ảnh ứng viên xuống máy và đăng khoảng
27 MB ảnh lên web. Không dọn thì ổ D đầy dần, còn trang web vượt hạn mức 1 GB của
GitHub Pages sau khoảng một tháng — lúc đó cả tờ báo ngừng hoạt động.

Số ngày giữ lại đặt trong config, mục `storage`. Luôn giữ ngày hôm nay.

Chạy tay (xem trước mà không xóa):  python pipeline/housekeeping.py --dry-run
"""
from __future__ import annotations
import re, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from datetime import timedelta
from common import setup_logging, DATA, RAW, LOGS, SITE_DATA, ISSUES, load_config, now_vn

log = setup_logging()
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DEFAULTS = {"keep_issue_days": 10, "keep_candidate_days": 2, "keep_raw_days": 7, "keep_log_days": 30}


def _mb(p: Path) -> float:
    if p.is_file():
        return p.stat().st_size / 1048576
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576


def _day_of(p: Path) -> str | None:
    m = DAY_RE.search(p.name)
    return m.group(0) if m else None


def _newest_issue() -> str | None:
    days = sorted((p.stem for p in ISSUES.glob("*.json") if DAY_RE.fullmatch(p.stem)), reverse=True)
    return days[0] if days else None


def _stale(base: Path, keep: int, want_dir: bool, protect: str | None = None) -> list[Path]:
    """Các mục theo ngày cần xóa: cũ hơn `keep` ngày tính từ hôm nay.

    Tính theo NGÀY THẬT, không phải "giữ N thư mục mới nhất": nếu máy tắt cả tuần
    thì cách đếm thư mục sẽ giữ lại cả thư mục từ mấy tháng trước.
    Ngày viết dạng YYYY-MM-DD nên so sánh chuỗi là đủ.
    """
    if keep < 1 or not base.exists():
        return []
    cutoff = (now_vn() - timedelta(days=keep - 1)).strftime("%Y-%m-%d")
    out = []
    for p in sorted(base.iterdir()):
        if p.is_dir() != want_dir:
            continue
        d = _day_of(p)
        if d and d < cutoff and d != protect:
            out.append(p)
    return out


def _drop(paths: list[Path], dry: bool) -> tuple[int, float]:
    freed = 0.0
    for p in paths:
        freed += _mb(p)
        if not dry:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    return len(paths), round(freed, 1)


def reindex(dry: bool = False) -> list[str]:
    """index.json = đúng những số báo còn trên đĩa, để trang lưu trữ không trỏ vào ngày đã xóa."""
    from common import write_json
    days = sorted((p.stem for p in ISSUES.glob("*.json") if DAY_RE.fullmatch(p.stem)), reverse=True)
    if not dry:
        write_json(SITE_DATA / "index.json", {"issues": days})
    return days


def run(cfg: dict | None = None, dry: bool = False) -> dict:
    cfg = cfg or load_config()
    st = {**DEFAULTS, **(cfg.get("storage") or {})}
    # Số báo mới nhất KHÔNG bao giờ bị xóa, dù đã cũ: app luôn mở data/latest.json,
    # nhà đi vắng hai tuần về vẫn phải thấy số báo cuối cùng còn đủ ảnh.
    newest = _newest_issue()
    jobs = [
        ("ảnh đã đăng", SITE_DATA / "img", st["keep_issue_days"], True, newest),
        ("số báo cũ", ISSUES, st["keep_issue_days"], False, newest),
        ("ảnh ứng viên", DATA / "candidates" / "img", st["keep_candidate_days"], True, None),
        ("ứng viên cũ", DATA / "candidates", st["keep_raw_days"], False, None),
        ("tin thô", RAW, st["keep_raw_days"], False, None),
        ("log", LOGS, st["keep_log_days"], False, None),
    ]
    out, total = {}, 0.0
    for name, base, keep, want_dir, protect in jobs:
        n, freed = _drop(_stale(base, keep, want_dir, protect), dry)
        if n:
            out[name] = {"xoa": n, "mb": freed}
            total += freed
    days = reindex(dry)
    out["tong_mb"] = round(total, 1)
    out["con_lai_so_bao"] = len(days)
    if total:
        log.info("Dọn dẹp%s: giải phóng %.1f MB (%s)", " (thử)" if dry else "", total,
                 ", ".join(f"{k} {v['xoa']}" for k, v in out.items() if isinstance(v, dict)))
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="chỉ xem sẽ xóa gì, không xóa thật")
    a = ap.parse_args()
    print(run(dry=a.dry_run))
