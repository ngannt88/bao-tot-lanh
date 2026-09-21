"""Chọn bài cân bằng chuyên mục, viết lại, xuất số báo cho site."""
from __future__ import annotations
from collections import Counter
from common import (setup_logging, write_json, read_json, ISSUES, SITE_DATA, REVIEW, today_str, now_vn, slug)
from rewrite import rewrite_article

log = setup_logging()


def select_candidates(scored: list[dict], cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Trả (tự_động, hàng_chờ, loại). Ưu tiên điểm cao, đủ mục 'required', không quá max_per_issue."""
    th_auto = cfg["scoring"]["threshold_auto"]
    th_rev = cfg["scoring"]["threshold_review"]
    auto = sorted([a for a in scored if a["score"] is not None and a["score"] >= th_auto],
                  key=lambda a: (-a["score"], a.get("age_h") or 99))
    review = [a for a in scored if a["score"] is not None and th_rev <= a["score"] < th_auto]
    rejected = [dict(a, rejected_by="score") for a in scored if a["score"] is None or a["score"] < th_rev]
    return auto, review, rejected


def pick_balanced(auto: list[dict], cfg: dict, n: int, extra: int = 4) -> list[dict]:
    """Chọn n + extra bài (dự phòng vì tầng 4 có thể loại tiếp), đảm bảo mỗi mục required có ≥1."""
    secs = {s["id"]: s for s in cfg["sections"]}
    chosen, count, used = [], Counter(), set()
    # 1) mỗi mục bắt buộc lấy bài điểm cao nhất
    for sid, s in secs.items():
        if not s.get("required"):
            continue
        for a in auto:
            if a["id"] not in used and a.get("section") == sid:
                chosen.append(a); used.add(a["id"]); count[sid] += 1
                break
    # 2) lấp đầy theo điểm, tôn trọng max_per_issue (nới 1 cho dự phòng)
    for a in auto:
        if len(chosen) >= n + extra:
            break
        sid = a.get("section")
        if a["id"] in used or sid not in secs:
            continue
        if count[sid] >= secs[sid].get("max_per_issue", 2) + 1:
            continue
        chosen.append(a); used.add(a["id"]); count[sid] += 1
    return chosen


def finalize(picked: list[dict], cfg: dict, n: int) -> list[dict]:
    """Cắt về đúng n bài, lần cuối ép max_per_issue, ưu tiên giữ đủ mục required."""
    secs = {s["id"]: s for s in cfg["sections"]}
    out, count = [], Counter()
    required_left = {sid for sid, s in secs.items() if s.get("required")}
    # trước tiên giữ 1 bài mỗi mục required
    for a in picked:
        sid = a["rewritten"].get("section") or a.get("section")
        if sid in required_left:
            out.append(a); count[sid] += 1; required_left.discard(sid)
    for a in picked:
        if len(out) >= n:
            break
        if a in out:
            continue
        sid = a["rewritten"].get("section") or a.get("section")
        if count[sid] >= secs.get(sid, {}).get("max_per_issue", 2):
            continue
        out.append(a); count[sid] += 1
    return out[:n]


def to_issue(articles: list[dict], cfg: dict, day: str) -> dict:
    secs = {s["id"]: s for s in cfg["sections"]}
    items = []
    for i, a in enumerate(articles):
        rw = a["rewritten"]
        sid = rw.get("section") or a.get("section")
        s = secs.get(sid, {"name": "Khác", "emoji": "📰"})
        items.append({
            "id": a["id"],
            "slug": slug(rw["versions"][cfg["readers"][0]["id"]]["title"]),
            "order": i + 1,
            "section": sid, "section_name": s["name"], "emoji": s["emoji"],
            "tags": rw.get("tags", []),
            "image_alt": rw.get("image_alt", ""),
            "versions": rw["versions"],
            "activities": rw.get("activities", []),
            "question": rw.get("question", ""),
            "fun_fact": rw.get("fun_fact", ""),
            "source_name": a["source_name"],   # để cha mẹ đối chiếu; app trẻ KHÔNG hiện link
            "source_url": a["url"],
            "score": a.get("score"),
        })
    return {
        "date": day,
        "paper": cfg["paper"]["name"],
        "tagline": cfg["paper"]["tagline"],
        "generated_at": now_vn().isoformat(timespec="seconds"),
        "readers": [{"id": r["id"], "name": r["name"], "age": r["age"]} for r in cfg["readers"]],
        "sections": [{"id": s["id"], "name": s["name"], "emoji": s["emoji"]} for s in cfg["sections"]],
        "articles": items,
    }


def build(auto: list[dict], review: list[dict], rejected_rules: list[dict], rejected_score: list[dict],
          cfg: dict, day: str | None = None, dry_run: bool = False) -> dict | None:
    day = day or today_str()
    n = cfg["paper"]["articles_per_issue"]
    picked = pick_balanced(auto, cfg, n)
    log.info("Chọn %d ứng viên để viết lại (mục tiêu %d bài)", len(picked), n)
    if dry_run:
        return None
    done, dropped4 = [], []
    for a in picked:
        r = rewrite_article(a, cfg)
        if r is None:
            continue
        if r.get("rejected_by"):
            dropped4.append(r)
        else:
            done.append(r)
        if len([d for d in done]) >= n + 1 and all(
                any((d["rewritten"].get("section") or d.get("section")) == s["id"] for d in done)
                for s in cfg["sections"] if s.get("required")):
            break
    final = finalize(done, cfg, n)
    if not final:
        log.error("Không có bài nào qua được tầng 4, không xuất số báo.")
        return None
    issue = to_issue(final, cfg, day)
    write_json(ISSUES / f"{day}.json", issue)
    write_json(SITE_DATA / "latest.json", issue)
    # danh mục các số để app tra cứu lịch sử
    index = read_json(SITE_DATA / "index.json", {"issues": []})
    index["issues"] = sorted({*index["issues"], day}, reverse=True)[:90]
    write_json(SITE_DATA / "index.json", index)
    # Báo cáo cho cha mẹ: hàng chờ + bị loại (không lên site)
    write_json(REVIEW / f"{day}.json", {
        "date": day,
        "published": [{"id": a["id"], "title": a["title"], "score": a["score"], "section": a.get("section"),
                       "source": a["source_name"], "url": a["url"]} for a in final],
        "review_queue": [{"id": a["id"], "title": a["title"], "score": a["score"], "reason": a.get("reason"),
                          "section": a.get("section"), "url": a["url"]} for a in review],
        "rejected_rules": [{"title": a["title"], "why": a["reject_reasons"], "url": a["url"]} for a in rejected_rules],
        "rejected_score": [{"title": a["title"], "score": a["score"], "why": a.get("reason"), "url": a["url"]}
                           for a in rejected_score],
        "rejected_rewrite": [{"title": a["title"], "why": a["reject_reasons"], "url": a["url"]} for a in dropped4],
    })
    log.info("Xuất số báo %s: %d bài — %s", day, len(final),
             ", ".join(f"{i['emoji']}{i['section']}" for i in issue["articles"]))
    return issue
