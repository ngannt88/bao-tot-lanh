"""Dịch bài từ nguồn tiếng Anh sang tiếng Việt.

Nguyên tắc: DỊCH SÁT, không viết lại, không tóm tắt, không thêm bài học.
Giữ nguyên số đoạn, thứ tự, ảnh và chú thích của bài gốc; chỉ đổi ngôn ngữ.

Định dạng trao đổi là VĂN BẢN CÓ ĐÁNH DẤU, không phải JSON: tiếng Việt dùng rất nhiều
dấu nháy kép nên ép model trả JSON thì hỏng cú pháp khoảng một nửa số lần.
Bài dài được chia lô để trả lời không bị cắt giữa chừng.
"""
from __future__ import annotations
import re
import concurrent.futures as cf
from ai import ask_text, AIError
from common import setup_logging

log = setup_logging()
PARALLEL = 3          # số bài dịch cùng lúc
CHUNK_PARAS = 10      # số đoạn mỗi lần gọi
CHUNK_CHARS = 4000    # hoặc cắt lô khi đủ ngần này ký tự
MAX_CHARS = 18000     # dài hơn nữa thì BỎ bài, không đăng bản cụt đuôi
TEXT_KINDS = ("p", "h", "q", "li")
MARK = re.compile(r"^@@([A-Z]+\d*)@@\s*$", re.M)


def _system(cfg: dict) -> str:
    rules = (cfg.get("translate", {}).get("rules") or "").strip()
    return f"""Bạn là người dịch báo chuyên nghiệp, dịch tin tức tiếng Anh sang tiếng Việt cho một tờ báo
dành cho trẻ em Việt Nam 7 đến 11 tuổi. Bài dịch sẽ được đăng NGUYÊN VĂN cho trẻ đọc.

QUY TẮC DỊCH:
{rules}

ĐỊNH DẠNG BẮT BUỘC
Đầu vào gồm nhiều khối, mỗi khối mở đầu bằng một dòng đánh dấu như @@TITLE@@, @@SAPO@@, @@P1@@, @@C1@@.
Bạn trả về ĐÚNG những dòng đánh dấu đó, theo ĐÚNG thứ tự, mỗi dòng đánh dấu nằm riêng một dòng,
và ngay dưới nó là phần đã dịch sang tiếng Việt.
- KHÔNG thêm, KHÔNG bớt, KHÔNG đổi tên bất kỳ dòng đánh dấu nào.
- KHÔNG viết lời dẫn, KHÔNG giải thích, KHÔNG dùng markdown, KHÔNG dùng JSON.
- Nếu một khối chỉ là quảng cáo, lời mời đăng ký nhận bản tin, hay điều hướng của trang web,
  hãy để phần dưới dòng đánh dấu đó TRỐNG.
- Giữ nguyên nội dung nhiều dòng nếu bản gốc có nhiều dòng.

Ví dụ đầu ra đúng:
@@TITLE@@
Bí mật của loài cá voi xanh
@@P1@@
Cá voi xanh là loài vật lớn nhất từng sống trên Trái Đất."""


def _parse(text: str) -> dict[str, str]:
    """Tách văn bản có đánh dấu thành {khóa: nội dung}."""
    parts, out = MARK.split(text), {}
    # parts = [phần đầu, key1, nội dung1, key2, nội dung2, ...]
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1].strip()
    return out


def _build(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"@@{k}@@\n{v}" for k, v in pairs)


def _ask_block(pairs: list[tuple[str, str]], cfg: dict, model: str) -> dict[str, str] | None:
    keys = [k for k, _ in pairs]
    prompt = ("Dịch phần sau sang tiếng Việt, giữ nguyên các dòng đánh dấu.\n\n" + _build(pairs)
              + f"\n\nTrả lại đúng {len(keys)} dòng đánh dấu: " + ", ".join(f"@@{k}@@" for k in keys))
    try:
        raw = ask_text(prompt, system=_system(cfg), model=model, thinking=0, timeout=420)
    except AIError as e:
        log.warning("Lô dịch lỗi: %s", str(e)[:100])
        return None
    got = _parse(raw)
    missing = [k for k in keys if k not in got]
    if missing:
        log.warning("Lô dịch thiếu %d/%d khối: %s", len(missing), len(keys), ", ".join(missing[:4]))
        return None
    return got


# Tên riêng tiếng Việt KHÁC hẳn tên tiếng Anh nên không tìm lại được trong tiêu đề gốc
# ("Japan" → "Nhật Bản"). Không giữ danh sách này thì tiêu đề dịch ra "ở nhật bản", trông
# như viết sai chính tả. Chỉ so theo CỤM, không so từng từ, để "anh", "mặt", "sao", "nam"
# đứng một mình vẫn được hạ xuống bình thường.
_PROPER = tuple(x.split() for x in (
    "việt nam", "nhật bản", "hàn quốc", "triều tiên", "trung quốc", "hoa kỳ", "ấn độ",
    "thái lan", "hà nội", "sài gòn", "đà nẵng", "hạ long", "trường sa", "hoàng sa",
    "trái đất", "mặt trời", "mặt trăng", "dải ngân hà", "hệ mặt trời",
    "sao hỏa", "sao kim", "sao mộc", "sao thổ", "sao thủy", "bắc cực", "nam cực",
    "thái bình dương", "đại tây dương", "ấn độ dương", "bắc băng dương", "biển đông",
    "châu á", "châu âu", "châu phi", "châu mỹ", "châu đại dương", "đông nam á",
    "bắc mỹ", "nam mỹ", "ngũ đại hồ", "tây ban nha", "bồ đào nha", "ả rập",
))


def _fix_title_case(vi: str, en: str) -> str:
    """Model hay bắt chước Title Case của tiêu đề tiếng Anh ("Những Con Số Kỳ Diệu").
    Tiếng Việt chỉ viết hoa chữ đầu và tên riêng, nên hạ xuống, giữ lại từ nào vốn
    là tên riêng (xuất hiện y nguyên trong tiêu đề gốc, như NASA, Messi, Paris)."""
    words = vi.split()
    if len(words) < 3:
        return vi
    upper = sum(1 for w in words[1:] if w[:1].isupper())
    if upper / max(1, len(words) - 1) < 0.5:          # không phải Title Case → để yên
        return vi
    keep = {w.strip(".,:;!?'\"") for w in en.split() if w[:1].isupper()}
    bares = [w.strip(".,:;!?'\"") for w in words]
    low = [b.lower() for b in bares]
    proper = [False] * len(words)
    for ph in _PROPER:                       # đánh dấu các cụm tên riêng tiếng Việt
        for i in range(len(low) - len(ph) + 1):
            if low[i:i + len(ph)] == ph:
                for k in range(i, i + len(ph)):
                    proper[k] = True
    out = [words[0]]
    for i, w in enumerate(words[1:], 1):
        # len > 1: "Ở" một chữ cũng thỏa isupper(), nếu không chặn thì "ở NASA" thành "Ở NASA"
        keep_it = proper[i] or bares[i] in keep or (bares[i].isupper() and len(bares[i]) > 1)
        out.append(w if keep_it else w[:1].lower() + w[1:])
    return " ".join(out)


def _chunks(paras: list[str]) -> list[tuple[int, list[str]]]:
    out, cur, start, size = [], [], 0, 0
    for i, t in enumerate(paras):
        cur.append(t); size += len(t)
        if len(cur) >= CHUNK_PARAS or size >= CHUNK_CHARS:
            out.append((start, cur)); start, cur, size = i + 1, [], 0
    if cur:
        out.append((start, cur))
    return out


def translate_article(a: dict, cfg: dict) -> dict | None:
    """Trả bản đã dịch, hoặc None nếu thất bại (bài bị bỏ, không đăng bản tiếng Anh)."""
    model = cfg.get("translate", {}).get("model", "sonnet")
    idx = [i for i, b in enumerate(a.get("blocks", [])) if b.get("t") in TEXT_KINDS]
    paras = [a["blocks"][i].get("text", "") for i in idx]
    total = sum(len(t) for t in paras)
    if total > MAX_CHARS:
        # Trước đây phần đuôi bị thay bằng chuỗi rỗng rồi lọc bỏ: bài vẫn lên báo
        # nhưng mất đoạn kết và không ai biết. Bỏ hẳn bài thì trung thực hơn.
        log.warning("Bỏ bài quá dài để dịch (%d ký tự): %s", total, a["title"][:50])
        return None
    captions = [im.get("caption", "") for im in a.get("images", [])]

    parts = _chunks(paras)
    vi_paras: list[str] = []
    head: dict[str, str] = {}
    for k, (start, chunk) in enumerate(parts):
        pairs: list[tuple[str, str]] = []
        if k == 0:
            pairs.append(("TITLE", a.get("title", "")))
            if a.get("sapo"):
                pairs.append(("SAPO", a["sapo"]))
            for j, cap in enumerate(captions):
                if cap:
                    pairs.append((f"C{j}", cap))
        # Chỉ gửi đoạn có chữ. Gửi kèm khối rỗng thì model hay lược luôn dòng đánh dấu
        # của khối đó, thiếu dấu là cả lô bị coi như hỏng và mất cả bài.
        pairs += [(f"P{start + j}", t) for j, t in enumerate(chunk) if t.strip()]
        if not pairs:
            vi_paras.extend("" for _ in chunk)
            continue
        got = _ask_block(pairs, cfg, model)
        if got is None:
            log.error("Dịch hỏng ở lô %d/%d: %s", k + 1, len(parts), a["title"][:55])
            return None
        vi_paras.extend(got.get(f"P{start + j}", "") for j in range(len(chunk)))
        if k == 0:
            head = got
    if not head.get("TITLE"):
        log.error("Dịch thiếu tiêu đề: %s", a["title"][:55])
        return None

    out = dict(a)
    blocks = [dict(b) for b in a.get("blocks", [])]
    for k, i in enumerate(idx):
        blocks[i]["text"] = vi_paras[k].strip()
    out["blocks"] = [b for b in blocks if b.get("t") == "img" or b.get("text")]
    if captions:
        out["images"] = [dict(im, caption=head.get(f"C{j}", im.get("caption", "")).strip())
                         for j, im in enumerate(a.get("images", []))]
    out.update(
        title_original=a.get("title", ""),
        title=_fix_title_case(head["TITLE"].strip(), a.get("title", "")),
        sapo=head.get("SAPO", "").strip(),
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
