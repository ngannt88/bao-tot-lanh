"""TẦNG 4 — Lấy toàn văn, AI (Sonnet) viết lại cho từng bé + hoạt động kèm theo."""
from __future__ import annotations
import json
import requests, trafilatura
from ai import ask_json, AIError
from common import setup_logging, word_count

log = setup_logging()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BaoTotLanh/0.1"}
MIN_BODY_WORDS = 120
MAX_BODY_CHARS = 9000


def fetch_fulltext(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        log.warning("Tải bài lỗi %s: %s", url[:60], str(e)[:80])
        return None
    txt = trafilatura.extract(r.text, include_comments=False, include_tables=False,
                              favor_recall=True, url=url)
    if not txt or word_count(txt) < MIN_BODY_WORDS:
        return None
    return txt[:MAX_BODY_CHARS]


def _schema(cfg: dict) -> dict:
    reader_ids = [r["id"] for r in cfg["readers"]]
    version = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "lead": {"type": "string"},
            "body": {"type": "string"},
            "words": {"type": "array", "items": {"type": "object",
                      "properties": {"w": {"type": "string"}, "m": {"type": "string"}},
                      "required": ["w", "m"]}},
        },
        "required": ["title", "lead", "body"],
    }
    return {
        "type": "object",
        "properties": {
            "safe": {"type": "boolean"},
            "unsafe_reason": {"type": "string"},
            "section": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "image_alt": {"type": "string"},
            "versions": {"type": "object",
                         "properties": {rid: version for rid in reader_ids},
                         "required": reader_ids},
            "activities": {"type": "array", "items": {"type": "object",
                           "properties": {"type": {"type": "string"}, "text": {"type": "string"}},
                           "required": ["type", "text"]}},
            "question": {"type": "string"},
            "fun_fact": {"type": "string"},
        },
        "required": ["safe", "versions", "activities", "question"],
    }


def _system(cfg: dict) -> str:
    readers = "\n".join(
        f"- id '{r['id']}' ({r['name']}, {r['age']} tuổi, lớp {r['grade']}): {r['words'][0]}–{r['words'][1]} chữ. "
        f"Phong cách: {r['style'].strip()} Sở thích: {', '.join(r['interests'])}."
        for r in cfg["readers"])
    acts = "\n".join(f"- type '{a['id']}' ({a['name']}): khi {a['when']}. {a['prompt_style']}"
                     for a in cfg["rewrite"]["activities"])
    secs = ", ".join(s["id"] for s in cfg["sections"])
    return f"""Bạn là biên tập viên tờ báo {cfg['paper']['name']} dành cho trẻ em Việt Nam.
Nhiệm vụ: đọc bài gốc, kiểm tra an toàn lần cuối, rồi viết lại thành các bản cho từng bé.

BƯỚC 1 — AN TOÀN: nếu toàn văn lộ ra nội dung không hợp trẻ em (bạo lực, chết chóc, tiền bạc,
tranh cãi, quảng cáo trá hình, chính trị, gây sợ) mà tiêu đề không cho thấy → safe=false,
ghi unsafe_reason, và versions có thể để chuỗi rỗng. Nếu bài không đủ nội dung để viết
lại tử tế (chỉ là tin vắn, lịch, thông báo) → safe=false với lý do 'khong-du-noi-dung'.

BƯỚC 2 — VIẾT LẠI (khi safe=true), mỗi bản là một bài hoàn chỉnh độc lập:
{readers}

QUY TẮC CHUNG:
{cfg['rewrite']['rules'].strip()}
- Nếu bài gốc là tiếng Anh: dịch ý và viết lại tự nhiên bằng tiếng Việt, không dịch máy.
- 'title' hấp dẫn nhưng trung thực, ≤ 12 chữ. 'lead' là 1 câu tóm gọn. 'body' tách đoạn bằng "\\n\\n".
- 'words': 2–3 từ hay trong bài với nghĩa giải thích ngắn (bé lớn thêm từ tiếng Anh tương ứng trong ngoặc).
- 'image_alt': mô tả 1 câu hình minh họa nên vẽ cho bài (dùng để tạo/chọn ảnh).
- 'section': một trong [{secs}]. 'tags': 3–5 nhãn ngắn không dấu (vd 'bong-da', 'vu-tru').
- 'activities': 1–2 hoạt động phù hợp nhất theo danh sách dưới; 'question' là câu hỏi suy nghĩ bắt buộc;
  'fun_fact': một sự thật thú vị ngắn liên quan (nếu chắc chắn đúng, không thì bỏ trống).
{acts}

Trả về đúng JSON theo schema."""


def rewrite_article(a: dict, cfg: dict) -> dict | None:
    body = fetch_fulltext(a["url"])
    if not body:
        log.info("Bỏ (không lấy được toàn văn): %s", a["title"][:60])
        return None
    prompt = (f"NGUỒN: {a['source_name']} | NGÔN NGỮ: {a['lang']} | MỤC GỢI Ý: {a.get('section')}\n"
              f"TIÊU ĐỀ GỐC: {a['title']}\n\nTOÀN VĂN:\n{body}")
    try:
        res = ask_json(prompt, system=_system(cfg), model=cfg["scoring"].get("model_rewrite", "sonnet"),
                       schema=_schema(cfg), timeout=420)
    except AIError as e:
        log.error("Viết lại lỗi: %s — %s", a["title"][:50], e)
        return None
    if not res.get("safe"):
        log.info("AI loại ở tầng 4 (%s): %s", res.get("unsafe_reason", "?"), a["title"][:60])
        return dict(a, rejected_by="rewrite", reject_reasons=[res.get("unsafe_reason", "khong-an-toan")])
    # Kiểm tra độ dài từng bản, cảnh báo nếu lệch quá
    for r in cfg["readers"]:
        v = res["versions"].get(r["id"]) or {}
        wc = word_count(v.get("body", ""))
        lo, hi = r["words"]
        if not (lo * 0.6 <= wc <= hi * 1.6):
            log.warning("Bản %s dài %d chữ (mục tiêu %d–%d): %s", r["id"], wc, lo, hi, a["title"][:40])
    return dict(a, rewritten=res)
