"""TẦNG 3 — AI (Haiku) chấm điểm hàng loạt theo tiêu đề + mô tả. Một lần gọi cho ~40 bài."""
from __future__ import annotations
import json
from ai import ask_json
from common import setup_logging

log = setup_logging()
BATCH = 40

SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 10},
                    "section": {"type": "string"},
                    "reason": {"type": "string"},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "score", "section", "reason"],
            },
        }
    },
    "required": ["scores"],
}


def _system(cfg: dict) -> str:
    secs = "\n".join(
        f"- {s['id']}: {s['name']}. Nhận: {s['what'].strip()} Không nhận: {s['not'].strip()}"
        for s in cfg["sections"])
    return (cfg["scoring"]["criteria"].strip()
            + "\n\nCHUYÊN MỤC (chọn đúng một id, hoặc 'khong-phu-hop'):\n" + secs
            + "\n\nTrả về đúng JSON theo schema, 'reason' ≤ 25 chữ tiếng Việt, "
              "'flags' liệt kê vấn đề nếu có (vd 'bao-luc', 'quang-cao', 'tien-bac', 'giat-gan', 'kho-viet-lai').")


def score_articles(articles: list[dict], cfg: dict) -> list[dict]:
    if not articles:
        return []
    system = _system(cfg)
    model = cfg["scoring"].get("model_filter", "haiku")
    out = []
    for i in range(0, len(articles), BATCH):
        chunk = articles[i:i + BATCH]
        rows = [{"id": a["id"], "nguon": a["source_name"], "goi_y_muc": a.get("hint_section"),
                 "tieu_de": a["title"], "mo_ta": a.get("summary", "")[:350]} for a in chunk]
        prompt = ("Chấm điểm các bài sau. Trả về mảng scores có đủ mọi id.\n\n"
                  + json.dumps(rows, ensure_ascii=False, indent=0))
        try:
            res = ask_json(prompt, system=system, model=model, schema=SCHEMA)
        except Exception as e:
            log.error("Chấm điểm lô %d lỗi: %s", i // BATCH + 1, e)
            for a in chunk:
                out.append(dict(a, score=None, section=None, reason="AI lỗi", flags=["ai-loi"]))
            continue
        by_id = {s["id"]: s for s in res.get("scores", [])}
        for a in chunk:
            s = by_id.get(a["id"])
            if not s:
                out.append(dict(a, score=None, section=None, reason="AI bỏ sót", flags=["ai-bo-sot"]))
                continue
            out.append(dict(a, score=int(s["score"]), section=s.get("section"),
                            reason=s.get("reason", ""), flags=s.get("flags") or []))
    scored = [a for a in out if a["score"] is not None]
    if scored:
        avg = sum(a["score"] for a in scored) / len(scored)
        log.info("Tầng 3: chấm %d bài, điểm TB %.1f, ≥8: %d, 6–7: %d",
                 len(scored), avg, sum(a["score"] >= 8 for a in scored),
                 sum(6 <= a["score"] <= 7 for a in scored))
    return out
