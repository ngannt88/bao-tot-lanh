"""Dịch bài từ nguồn tiếng Anh sang tiếng Việt.

Nguyên tắc: DỊCH SÁT, không viết lại, không tóm tắt, không thêm bài học.
Giữ nguyên số đoạn, thứ tự, ảnh và chú thích của bài gốc; chỉ đổi ngôn ngữ.
Bài dịch được đánh dấu để app hiện "Dịch từ <nguồn>" và góc cha mẹ vẫn giữ link gốc.
"""
from __future__ import annotations
import json
import concurrent.futures as cf
from ai import ask_json, AIError
from common import setup_logging

log = setup_logging()
PARALLEL = 3          # số bài dịch cùng lúc
MAX_CHARS = 9000      # cắt bớt bài quá dài trước khi dịch (bài cho trẻ hiếm khi chạm ngưỡng)
TEXT_KINDS = ("p", "h", "q", "li")


def _system(cfg: dict) -> str:
    rules = (cfg.get("translate", {}).get("rules") or "").strip()
    return f"""Bạn là người dịch báo chuyên nghiệp, dịch tin tức tiếng Anh sang tiếng Việt cho một tờ báo
dành cho trẻ em Việt Nam 7 đến 11 tuổi. Bài dịch sẽ được đăng NGUYÊN VĂN cho trẻ đọc.

QUY TẮC:
{rules}

ĐẦU VÀO là JSON gồm: title, sapo, paras (mảng đoạn văn đã đánh số theo thứ tự), captions (mảng chú thích ảnh).
ĐẦU RA BẮT BUỘC: chỉ một JSON object, không lời dẫn, không markdown:
{{"title":"...","sapo":"...","paras":["...","..."],"captions":["...","..."]}}
- Mảng paras phải có ĐÚNG số phần tử như đầu vào, đúng thứ tự. Đoạn nào rỗng thì trả chuỗi rỗng.
- Mảng captions cũng phải đúng số phần tử như đầu vào.
- title ngắn gọn, hấp dẫn, trung thực với bản gốc, không thêm dấu chấm than.
- Nếu một đoạn chỉ là quảng cáo, lời mời đăng ký nhận bản tin, hay điều hướng của trang web,
  hãy trả về chuỗi rỗng cho đoạn đó."""


def _needs_translation(a: dict) -> bool:
    return a.get("lang") == "en" and not a.get("translated")


def translate_article(a: dict, cfg: dict) -> dict | None:
    """Trả về bản đã dịch, hoặc None nếu dịch thất bại (bài sẽ bị bỏ, không đăng bản tiếng Anh)."""
    idx = [i for i, b in enumerate(a.get("blocks", [])) if b.get("t") in TEXT_KINDS]
    paras, total = [], 0
    for i in idx:
        t = a["blocks"][i].get("text", "")
        total += len(t)
        paras.append(t if total <= MAX_CHARS else "")
    captions = [im.get("caption", "") for im in a.get("images", [])]
    payload = {"title": a.get("title", ""), "sapo": a.get("sapo", ""), "paras": paras, "captions": captions}
    prompt = ("Dịch bài báo sau sang tiếng Việt.\n\n" + json.dumps(payload, ensure_ascii=False)
              + f'\n\nTrả JSON đúng khuôn, paras đúng {len(paras)} phần tử, captions đúng {len(captions)} phần tử.')
    model = cfg.get("translate", {}).get("model", "sonnet")
    try:
        res = ask_json(prompt, system=_system(cfg), model=model, thinking=0, timeout=420)
    except AIError as e:
        log.error("Dịch lỗi (%s): %s", str(e)[:80], a["title"][:60])
        return None
    if not isinstance(res, dict) or not res.get("title"):
        log.error("Dịch trả về sai khuôn: %s", a["title"][:60])
        return None
    vi_paras = res.get("paras") or []
    if len(vi_paras) != len(paras):
        log.error("Dịch lệch số đoạn (%d/%d): %s", len(vi_paras), len(paras), a["title"][:60])
        return None
    out = dict(a)
    blocks = [dict(b) for b in a.get("blocks", [])]
    for k, i in enumerate(idx):
        blocks[i]["text"] = str(vi_paras[k]).strip()
    out["blocks"] = [b for b in blocks if b.get("t") == "img" or b.get("text")]
    vi_caps = res.get("captions") or []
    if len(vi_caps) == len(captions):
        out["images"] = [dict(im, caption=str(vi_caps[j]).strip()) for j, im in enumerate(a.get("images", []))]
    out.update(
        title_original=a.get("title", ""),
        title=str(res["title"]).strip(),
        sapo=str(res.get("sapo") or "").strip(),
        translated=True,
        translated_from=a.get("source_name", ""),
        lang="vi-dich",
        words=sum(len(str(x).split()) for x in vi_paras),
    )
    log.info("Đã dịch: %s → %s", a["title"][:45], out["title"][:45])
    return out


def translate_all(cands: list[dict], cfg: dict) -> list[dict]:
    """Dịch tối đa max_per_issue bài tiếng Anh điểm cao nhất; bài dịch hỏng thì loại khỏi danh sách."""
    tc = cfg.get("translate", {})
    if not tc.get("enabled"):
        return [c for c in cands if c.get("lang") != "en"]
    todo = [c for c in cands if _needs_translation(c)]
    todo.sort(key=lambda c: -(c.get("score") or 0))
    limit = int(tc.get("max_per_issue", 6))
    picked, dropped = todo[:limit], todo[limit:]
    if not picked:
        return [c for c in cands if c.get("lang") != "en"]
    log.info("Dịch %d bài tiếng Anh (bỏ %d bài vượt hạn mức)", len(picked), len(dropped))
    with cf.ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        done = list(ex.map(lambda c: translate_article(c, cfg), picked))
    by_id = {c["id"]: t for c, t in zip(picked, done) if t is not None}
    failed = len(picked) - len(by_id)
    if failed:
        log.warning("%d bài dịch thất bại, đã loại khỏi số báo", failed)
    out = []
    for c in cands:
        if c.get("lang") != "en":
            out.append(c)
        elif c["id"] in by_id:
            out.append(by_id[c["id"]])
    return out
