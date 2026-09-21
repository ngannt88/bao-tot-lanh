"""Dịch bài từ nguồn tiếng Anh sang tiếng Việt.

Nguyên tắc: DỊCH SÁT, không viết lại, không tóm tắt, không thêm bài học.
Giữ nguyên số đoạn, thứ tự, ảnh và chú thích của bài gốc; chỉ đổi ngôn ngữ.
Bài dịch được đánh dấu để app hiện "Dịch từ <nguồn>" và góc cha mẹ vẫn giữ link gốc.

Bài dài được chia lô để trả lời của model không bị cắt giữa chừng (JSON hỏng).
"""
from __future__ import annotations
import json
import concurrent.futures as cf
from ai import ask_json, AIError
from common import setup_logging

log = setup_logging()
PARALLEL = 3          # số bài dịch cùng lúc
CHUNK_PARAS = 10      # số đoạn mỗi lần gọi; giữ nhỏ để tránh bị cắt output
CHUNK_CHARS = 4000    # hoặc cắt lô khi đủ ngần này ký tự
MAX_CHARS = 12000     # bài dài hơn thì bỏ phần đuôi
TEXT_KINDS = ("p", "h", "q", "li")


def _system(cfg: dict) -> str:
    rules = (cfg.get("translate", {}).get("rules") or "").strip()
    return f"""Bạn là người dịch báo chuyên nghiệp, dịch tin tức tiếng Anh sang tiếng Việt cho một tờ báo
dành cho trẻ em Việt Nam 7 đến 11 tuổi. Bài dịch sẽ được đăng NGUYÊN VĂN cho trẻ đọc.

QUY TẮC:
{rules}

ĐẦU VÀO là JSON có thể gồm: title, sapo, paras (mảng đoạn văn theo thứ tự), captions (mảng chú thích ảnh).
Trường nào không có trong đầu vào thì KHÔNG trả về trường đó.
ĐẦU RA BẮT BUỘC: chỉ một JSON object, không lời dẫn, không markdown, không xuống dòng thừa.
- Mảng paras phải có ĐÚNG số phần tử như đầu vào và đúng thứ tự. Đoạn rỗng trả chuỗi rỗng.
- Mảng captions cũng phải đúng số phần tử như đầu vào.
- title ngắn gọn, hấp dẫn, trung thực với bản gốc, không thêm dấu chấm than.
- Nếu một đoạn chỉ là quảng cáo, lời mời đăng ký nhận bản tin, hay điều hướng của trang web,
  hãy trả về chuỗi rỗng cho đoạn đó.
- Dùng dấu nháy kép chuẩn trong JSON; trong nội dung tiếng Việt hãy dùng nháy đơn hoặc nháy kép cong."""


def _chunks(paras: list[str]) -> list[tuple[int, list[str]]]:
    out, cur, start, size = [], [], 0, 0
    for i, t in enumerate(paras):
        cur.append(t); size += len(t)
        if len(cur) >= CHUNK_PARAS or size >= CHUNK_CHARS:
            out.append((start, cur)); start, cur, size = i + 1, [], 0
    if cur:
        out.append((start, cur))
    return out


def _ask(payload: dict, cfg: dict, model: str, note: str) -> dict | None:
    prompt = ("Dịch phần sau của bài báo sang tiếng Việt.\n\n" + json.dumps(payload, ensure_ascii=False)
              + f"\n\n{note} Chỉ trả JSON, không thêm chữ nào khác.")
    try:
        res = ask_json(prompt, system=_system(cfg), model=model, thinking=0, timeout=420)
    except AIError as e:
        log.warning("Lô dịch lỗi: %s", str(e)[:100])
        return None
    return res if isinstance(res, dict) else None


def translate_article(a: dict, cfg: dict) -> dict | None:
    """Trả bản đã dịch, hoặc None nếu thất bại (bài bị bỏ, không đăng bản tiếng Anh)."""
    model = cfg.get("translate", {}).get("model", "sonnet")
    idx = [i for i, b in enumerate(a.get("blocks", [])) if b.get("t") in TEXT_KINDS]
    paras, total = [], 0
    for i in idx:
        t = a["blocks"][i].get("text", "")
        total += len(t)
        paras.append(t if total <= MAX_CHARS else "")
    captions = [im.get("caption", "") for im in a.get("images", [])]

    parts = _chunks(paras)
    vi_paras: list[str] = []
    for k, (start, chunk) in enumerate(parts):
        payload = {"paras": chunk}
        if k == 0:
            payload = {"title": a.get("title", ""), "sapo": a.get("sapo", ""), "paras": chunk}
            if captions:
                payload["captions"] = captions
        res = _ask(payload, cfg, model, f"paras phải đúng {len(chunk)} phần tử.")
        if not res or not isinstance(res.get("paras"), list) or len(res["paras"]) != len(chunk):
            log.error("Dịch hỏng ở lô %d/%d: %s", k + 1, len(parts), a["title"][:55])
            return None
        vi_paras.extend(str(x) for x in res["paras"])
        if k == 0:
            head = res
    if not head.get("title"):
        log.error("Dịch thiếu tiêu đề: %s", a["title"][:55])
        return None

    out = dict(a)
    blocks = [dict(b) for b in a.get("blocks", [])]
    for k, i in enumerate(idx):
        blocks[i]["text"] = vi_paras[k].strip()
    out["blocks"] = [b for b in blocks if b.get("t") == "img" or b.get("text")]
    vi_caps = head.get("captions") or []
    if captions and len(vi_caps) == len(captions):
        out["images"] = [dict(im, caption=str(vi_caps[j]).strip()) for j, im in enumerate(a.get("images", []))]
    out.update(
        title_original=a.get("title", ""),
        title=str(head["title"]).strip(),
        sapo=str(head.get("sapo") or "").strip(),
        translated=True,
        translated_from=a.get("source_name", ""),
        lang="vi-dich",
        words=sum(len(x.split()) for x in vi_paras),
    )
    log.info("Đã dịch (%d lô): %s", len(parts), out["title"][:60])
    return out


def translate_all(cands: list[dict], cfg: dict) -> list[dict]:
    """Dịch tối đa max_per_issue bài tiếng Anh điểm cao nhất; bài dịch hỏng thì loại khỏi danh sách."""
    tc = cfg.get("translate", {})
    if not tc.get("enabled"):
        return [c for c in cands if c.get("lang") != "en"]
    todo = [c for c in cands if c.get("lang") == "en" and not c.get("translated")]
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
