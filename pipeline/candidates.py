"""Chọn ứng viên cho cha mẹ duyệt: cân bằng chuyên mục, rồi tách nguyên văn từng bài."""
from __future__ import annotations
import concurrent.futures as cf
from collections import Counter
from common import setup_logging, write_json, read_json, DATA, today_str, now_vn

log = setup_logging()
CAND_DIR = DATA / "candidates"
CAND_IMG = CAND_DIR / "img"


def select(scored: list[dict], cfg: dict, has_scores: bool) -> list[dict]:
    """Trả danh sách ứng viên theo thứ tự ưu tiên (chưa tách nội dung)."""
    rv = cfg.get("review", {})
    n = rv.get("candidates_per_day", 12)
    min_score = rv.get("min_score_candidate", 6)
    secs = {s["id"]: s for s in cfg["sections"]}
    if has_scores:
        pool = [a for a in scored if a.get("score") is not None and a["score"] >= min_score]
        pool.sort(key=lambda a: (-a["score"], a.get("age_h") or 99))
        key = lambda a: a.get("section")
    else:
        # Không có AI: xoay vòng theo mục gợi ý của nguồn, bài mới trước
        pool = sorted(scored, key=lambda a: a.get("age_h") or 99)
        key = lambda a: a.get("hint_section")
        n = int(n * 1.5)
    chosen, count, used = [], Counter(), set()
    # mỗi mục bắt buộc lấy bài tốt nhất trước
    for sid, s in secs.items():
        if not s.get("required"):
            continue
        for a in pool:
            if a["id"] not in used and key(a) == sid:
                chosen.append(a); used.add(a["id"]); count[sid] += 1
                break
    cap = {sid: s.get("max_per_issue", 2) + 1 for sid, s in secs.items()}
    if not has_scores:
        # xoay vòng đều giữa các mục
        buckets: dict[str, list] = {}
        for a in pool:
            if a["id"] not in used:
                buckets.setdefault(key(a) or "khac", []).append(a)
        while len(chosen) < n and any(buckets.values()):
            for sid in list(buckets):
                if buckets[sid] and len(chosen) < n:
                    a = buckets[sid].pop(0); chosen.append(a); used.add(a["id"])
    else:
        for a in pool:
            if len(chosen) >= n:
                break
            sid = key(a)
            if a["id"] in used or count[sid] >= cap.get(sid, 2):
                continue
            chosen.append(a); used.add(a["id"]); count[sid] += 1
    log.info("Chọn %d ứng viên (%s)", len(chosen), "theo điểm AI" if has_scores else "không có AI, xoay vòng theo mục")
    return chosen


def extract_all(chosen: list[dict], day: str) -> tuple[list[dict], list[dict]]:
    from extract import extract_article
    img_dir = CAND_IMG / day
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda a: extract_article(a, img_dir), chosen))
    ok = [r for r in results if r.get("extracted_ok")]
    bad = [r for r in results if not r.get("extracted_ok")]
    for r in bad:
        log.info("Tách lỗi (%s): %s", r.get("extract_error"), r["title"][:60])
    log.info("Tách nguyên văn: %d thành công, %d lỗi", len(ok), len(bad))
    return ok, bad


def save(day: str, cfg: dict, candidates: list[dict], has_scores: bool, blocked: list[dict],
         rejected_score: list[dict], extract_failed: list[dict]) -> dict:
    payload = {
        "date": day,
        "generated_at": now_vn().isoformat(timespec="seconds"),
        "ai_scored": has_scores,
        "target": cfg["paper"]["articles_per_issue"],
        "sections": [{"id": s["id"], "name": s["name"], "emoji": s["emoji"]} for s in cfg["sections"]],
        "candidates": [{k: v for k, v in a.items() if k not in ("summary",)} for a in candidates],
        "rejected_rules": [{"title": a["title"], "why": a.get("reject_reasons"), "url": a["url"], "source": a["source_name"]} for a in blocked],
        "rejected_score": [{"title": a["title"], "score": a.get("score"), "why": a.get("reason"), "url": a["url"], "source": a["source_name"]} for a in rejected_score],
        "extract_failed": [{"title": a["title"], "why": a.get("extract_error"), "url": a["url"]} for a in extract_failed],
    }
    write_json(CAND_DIR / f"{day}.json", payload)
    return payload


def load(day: str | None = None) -> dict | None:
    day = day or today_str()
    return read_json(CAND_DIR / f"{day}.json", None)
