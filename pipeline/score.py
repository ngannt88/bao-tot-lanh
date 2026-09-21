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


def _truthy(v) -> bool:
    """true/'co'/'có'/'yes'/1 → True; false/'khong'/'không'/'no'/0 → False; không rõ → True (để cha mẹ xem)."""
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("false", "0", "no", "khong", "không", "k", "sai", "unsafe", "loai", "loại"):
        return False
    return True


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
            + '{"scores":[{"id":"<id>","score":<số nguyên 0-10, thang 10>,"section":"<id mục>","topic":"<1-2 từ không dấu>","reason":"<≤12 chữ>","flags":[]}]}\n'
            + "Đủ mọi id đã cho. JSON NÉN một dòng, không thụt lề, không xuống dòng. "
              "Bài dưới 6 điểm: bỏ hẳn 'reason' và 'flags' (chỉ id, score, section). "
              "Bài từ 6 điểm: 'reason' ≤ 8 chữ, 'flags' chỉ khi có vấn đề (vd 'tien-bac','giat-gan','chinh-sach').")


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
                  + '\n\nCHỈ TRẢ JSON NÉN MỘT DÒNG {"scores":[{"id":"..","score":n,"section":"..","topic":".."},...]} thang 0–10, '
                    'đủ mọi id, mọi bài đều có "topic"; chỉ bài ≥6 mới thêm "reason" ≤ 8 chữ. Không thêm chữ nào khác.')
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
                            topic=str(_pick(x, "topic", "chu_de") or "")[:40].lower(),
                            flags=[str(f) for f in (x.get("flags") or []) if f]))
    scored = [a for a in out if a["score"] is not None]
    missed = len(out) - len(scored)
    if scored:
        avg = sum(a["score"] for a in scored) / len(scored)
        log.info("Tầng 3: chấm %d bài (bỏ sót %d), điểm TB %.1f, ≥8: %d, 6–7: %d",
                 len(scored), missed, avg, sum(a["score"] >= 8 for a in scored),
                 sum(6 <= a["score"] <= 7 for a in scored))
    return out


# ---------------------------------------------------------------------------
# VÒNG 2 — kiểm tra lại ỨNG VIÊN đã có toàn văn (ít bài, đọc 1.200 chữ đầu, được suy nghĩ)
# ---------------------------------------------------------------------------
VERIFY_BATCH = 8
VERIFY_THINKING = 2000


def _verify_system(cfg: dict) -> str:
    return (cfg["scoring"]["criteria"].strip()
            + "\n\nBạn đang KIỂM TRA LẦN CUỐI các bài sắp lên báo cho trẻ 7 và 11 tuổi, dựa trên NỘI DUNG THẬT "
              "(đoạn đầu bài), không chỉ tiêu đề. Bài sẽ hiển thị NGUYÊN VĂN cho trẻ đọc.\n"
              "Với mỗi bài trả: 'safe' (true/false: có nội dung không hợp trẻ như chết chóc, bạo lực, tiền bạc, "
              "chính sách, tranh cãi, quảng cáo, người lớn?), 'score' 0–10 theo tiêu chí, 'reason' ≤ 10 chữ.\n"
              "LƯU Ý: một số bài đang là tiếng Anh. Chúng SẼ ĐƯỢC DỊCH SÁT sang tiếng Việt trước khi đăng, "
              "nên TUYỆT ĐỐI KHÔNG trừ điểm hay đánh dấu không an toàn chỉ vì bài viết bằng tiếng Anh. "
              "Hãy chấm đúng nội dung như thể bạn đang đọc bản tiếng Việt của nó.\n"
              "ĐẦU RA: chỉ JSON nén một dòng {\"scores\":[{\"id\":\"..\",\"safe\":true,\"score\":n,\"reason\":\"..\"}]}, đủ mọi id.")


def verify_candidates(cands: list[dict], cfg: dict) -> list[dict]:
    """Chấm lại theo nội dung thật. Trả về danh sách đã cập nhật score (lấy MIN hai vòng), safe, reason2."""
    if not cands:
        return []
    system = _verify_system(cfg)
    model = cfg["scoring"].get("model_verify", cfg["scoring"].get("model_filter", "haiku"))
    thinking = int(cfg["scoring"].get("thinking_verify", VERIFY_THINKING))
    chunks = [cands[i:i + VERIFY_BATCH] for i in range(0, len(cands), VERIFY_BATCH)]

    def _body(c: dict) -> str:
        txt = " ".join(b.get("text", "") for b in c.get("blocks", []) if b.get("t") in ("p", "h", "q", "li"))
        return txt[:1200]

    def _call(idx_chunk):
        idx, chunk = idx_chunk
        rows = [{"id": c["id"], "tieu_de": c["title"], "sapo": (c.get("sapo") or "")[:300], "doan_dau": _body(c)} for c in chunk]
        prompt = ("Kiểm tra các bài sau.\n\n" + json.dumps(rows, ensure_ascii=False)
                  + '\n\nCHỈ TRẢ JSON nén một dòng đúng khuôn {"scores":[{"id":"..","safe":true|false,"score":0-10,"reason":".."}]}, '
                    'đủ mọi id, reason bằng tiếng Việt CÓ DẤU ≤ 10 chữ. Không thêm chữ nào khác.')
        try:
            return idx, ask_json(prompt, system=system, model=model, thinking=thinking, timeout=420)
        except Exception as e:
            log.error("Kiểm tra lô %d lỗi: %s", idx + 1, e)
            return idx, None

    import concurrent.futures as cf
    results: dict[int, object] = {}
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        for idx, res in ex.map(_call, enumerate(chunks)):
            results[idx] = res
    out = []
    dropped = 0
    for idx, chunk in enumerate(chunks):
        by_id = {str(x.get("id")): x for x in _normalize(results.get(idx))} if results.get(idx) is not None else {}
        for c in chunk:
            x = by_id.get(c["id"])
            if not x:
                out.append(dict(c, verified=False))          # không kiểm được → giữ, để cha mẹ xem
                continue
            raw_safe = _pick(x, "safe", "an_toan", "an toan", "duyet", "phu_hop", "phu hop", "ok", "hop_le")
            safe = _truthy(raw_safe)
            s2 = _to_score(_pick(x, "score", "diem", "score2", "diem_so"))
            s1 = c.get("score")
            final = min(s1, s2) if (s1 is not None and s2 is not None) else (s2 if s2 is not None else s1)
            reason2 = str(_pick(x, "reason", "ly_do", "lydo", "nhan_xet", "ghi_chu") or "")[:120]
            if not safe:
                dropped += 1
            out.append(dict(c, verified=True, safe=safe, score1=s1, score2=s2, score=final,
                            reason=(c.get("reason") or ""), reason2=reason2))
    log.info("Vòng 2: kiểm %d ứng viên, %d bị đánh dấu không an toàn", len(out), dropped)
    return out
