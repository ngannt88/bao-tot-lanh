"""TẦNG 3 — AI (Haiku) chấm điểm hàng loạt theo tiêu đề + mô tả. Một lần gọi cho ~40 bài.
Đọc kết quả bao dung: model có thể trả mảng trần, tên trường khác, thang 100 — đều quy về chuẩn."""
from __future__ import annotations
import json
from ai import ask_json
from common import setup_logging

log = setup_logging()
BATCH = 40
PARALLEL = 3   # số lô chấm song song


def _normalize(res) -> list[dict]:
    """{"scores":[...]}, mảng trần, hay {id: {...}} → một mảng dict."""
    if isinstance(res, list):
        return [x for x in res if isinstance(x, dict)]
    if isinstance(res, dict):
        for k in ("scores", "ket_qua", "results", "items", "bai", "diem"):
            if isinstance(res.get(k), list):
                return [x for x in res[k] if isinstance(x, dict)]
        out = []
        for k, v in res.items():
            if isinstance(v, dict):
                out.append(dict(v, id=k))
            elif isinstance(v, (int, float, str)):
                out.append({"id": k, "score": v})
        return out
    return []


def _pick(x: dict, *keys):
    for k in keys:
        if x.get(k) not in (None, ""):
            return x[k]
    return None


def _num(v):
    try:
        return float(str(v).strip().split("/")[0].replace(",", "."))
    except (TypeError, ValueError):
        return None


def _to_score(v, scale: float = 1.0):
    f = _num(v)
    if f is None:
        return None
    return max(0, min(10, int(round(f / scale))))


def _system(cfg: dict) -> str:
    secs = "\n".join(
        f"- {s['id']}: {s['name']}. Nhận: {s['what'].strip()} Không nhận: {s['not'].strip()}"
        for s in cfg["sections"])
    return (cfg["scoring"]["criteria"].strip()
            + "\n\nCHUYÊN MỤC (chọn đúng một id, hoặc 'khong-phu-hop'):\n" + secs
            + "\n\nĐẦU RA BẮT BUỘC: chỉ một JSON object, không lời dẫn, không markdown, không giải thích ngoài JSON:\n"
            + '{"scores":[{"id":"<id>","score":<số nguyên 0-10, thang 10>,"section":"<id mục>","reason":"<≤12 chữ>","flags":[]}]}\n'
            + "Đủ mọi id đã cho. 'flags' chỉ khi có vấn đề (vd 'bao-luc','quang-cao','tien-bac','giat-gan','chinh-sach').")


def score_articles(articles: list[dict], cfg: dict) -> list[dict]:
    if not articles:
        return []
    system = _system(cfg)
    model = cfg["scoring"].get("model_filter", "haiku")
    chunks = [articles[i:i + BATCH] for i in range(0, len(articles), BATCH)]

    def _call(idx_chunk):
        idx, chunk = idx_chunk
        rows = [{"id": a["id"], "nguon": a["source_name"], "goi_y_muc": a.get("hint_section"),
                 "tieu_de": a["title"], "mo_ta": a.get("summary", "")[:300]} for a in chunk]
        prompt = ("Chấm điểm các bài sau.\n\n" + json.dumps(rows, ensure_ascii=False, indent=0)
                  + '\n\nCHỈ TRẢ JSON {"scores":[...]} thang 0–10, đủ mọi id, reason ≤ 8 chữ, không thêm chữ nào khác.')
        try:
            return idx, ask_json(prompt, system=system, model=model)
        except Exception as e:
            log.error("Chấm điểm lô %d lỗi: %s", idx + 1, e)
            return idx, None

    import concurrent.futures as cf
    results: dict[int, object] = {}
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as ex:      # vài lô cùng lúc: nhanh hơn, usage không đổi
        for idx, res in ex.map(_call, enumerate(chunks)):
            results[idx] = res
    out = []
    for idx, chunk in enumerate(chunks):
        res = results.get(idx)
        if res is None:
            for a in chunk:
                out.append(dict(a, score=None, section=None, reason="AI lỗi", flags=["ai-loi"]))
            continue
        items = _normalize(res)
        nums = [_num(x.get("score")) for x in items]
        scale = 10.0 if any(n is not None and n > 10 for n in nums) else 1.0   # model chấm thang 100 → chia 10
        by_id = {str(x.get("id")): x for x in items}
        for a in chunk:
            x = by_id.get(a["id"])
            sc = _to_score(x.get("score"), scale) if x else None
            if x is None or sc is None:
                out.append(dict(a, score=None, section=None, reason="AI bỏ sót", flags=["ai-bo-sot"]))
                continue
            out.append(dict(a, score=sc,
                            section=_pick(x, "section", "muc", "chuyen_muc") or a.get("hint_section"),
                            reason=str(_pick(x, "reason", "ly_do", "lydo", "giai_thich") or "")[:160],
                            flags=[str(f) for f in (x.get("flags") or []) if f]))
    scored = [a for a in out if a["score"] is not None]
    missed = len(out) - len(scored)
    if scored:
        avg = sum(a["score"] for a in scored) / len(scored)
        log.info("Tầng 3: chấm %d bài (bỏ sót %d), điểm TB %.1f, ≥8: %d, 6–7: %d",
                 len(scored), missed, avg, sum(a["score"] >= 8 for a in scored),
                 sum(6 <= a["score"] <= 7 for a in scored))
    return out
