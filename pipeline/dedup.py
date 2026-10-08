"""SOÁT TRÙNG — mỗi câu chuyện chỉ lên báo một lần.

Gom các ứng viên kể CÙNG MỘT CÂU CHUYỆN (cùng sự kiện, cùng phát hiện, cùng nhân vật với
cùng thành tích), giữ bài tốt nhất mỗi nhóm, và bỏ bài kể lại chuyện đã đăng mấy ngày gần đây.

Vì sao phải là MỘT lần gọi AI nhìn thấy toàn bộ danh sách: trước đây máy chấm tự đặt nhãn
"topic" cho từng lô bài riêng rẽ, nên cùng một chuyện mang nhãn khác nhau ở mỗi lô (5 bài
Nguyễn Thị Tâm ngày 03/10 ra 4 nhãn) và lọt hết lên báo. So chữ (không AI) cũng đã đo:
bắt được ca dễ nhưng sót khi cùng nhân vật được viết theo góc khác, và hai bài cùng chuyện
Tà Xùa gần như không có chữ chung.

Đã đo trên ứng viên thật 01–07/10 (07/10/2026): Haiku không suy nghĩ thất thường, mỗi lần
sót và gộp nhầm một kiểu (gộp cả "ASIAD" thành một chuyện, gộp biển mây Nha Trang với Ba Vì);
Haiku có suy nghĩ đúng hơn nhưng tốn gấp 5 lần token ra và ~70 giây; Sonnet không suy nghĩ
đúng nhất với ~200 token ra. Nên dùng scoring.model_dedup = sonnet.

Chạy SAU vòng 2 (bài đã tách được, điểm đã chấm theo nội dung) và TRƯỚC khi dịch
(không tốn công dịch bài trùng). AI lỗi thì bỏ qua bước này, báo vẫn ra như cũ.
"""
from __future__ import annotations
import math
import re
import unicodedata
from collections import Counter
from datetime import date, timedelta
from ai import ask_json
from common import setup_logging, read_json, ISSUES

log = setup_logging()
MAX_DROP_SHARE = 1 / 3   # AI đòi bỏ nhiều hơn thế → nghi gộp nhầm theo đề tài, không tin kết quả
NAME_COVER = 0.15        # bài phải chứa ≥ ngần này (theo trọng số) tên câu chuyện AI đặt, xem drop_repeats

SYSTEM = """Bạn là biên tập viên trực bàn của một tờ báo cho trẻ em. Việc duy nhất: tìm các bài KỂ CÙNG MỘT CÂU CHUYỆN để mỗi câu chuyện chỉ lên báo một lần.

CÙNG CÂU CHUYỆN = cùng AI (người, đội, con vật, công trình) + cùng LÀM GÌ / XẢY RA GÌ + cùng Ở ĐÂU, TRẬN NÀO, CUỘC THI NÀO.
Vẫn là cùng câu chuyện khi:
- các báo viết bằng chữ khác nhau, hoặc đứng ở góc khác nhau (tường thuật, chân dung, phỏng vấn, chùm ảnh);
- là chặng tiếp theo của CÙNG một cuộc thi, cùng người, cùng nội dung thi (vào chung kết rồi giành huy chương ở chính nội dung đó);
- một bài tiếng Anh, một bài tiếng Việt; hoặc cùng một bài đăng lại với tiêu đề hơi khác.

KHÁC câu chuyện khi khác dù chỉ MỘT trong ba yếu tố:
- cùng người nhưng việc khác: bàn thắng ở hai trận khác nhau, huy chương ở hai nội dung khác nhau, hai sự kiện khác nhau của cùng một thương hiệu;
- cùng việc nhưng người khác: hai học sinh khác nhau đoạt hai giải khác nhau, nhiều bài cùng một loạt ("Cuộc thi Lan tỏa năng lượng tích cực: ...") về những người khác nhau;
- cùng hiện tượng nhưng nơi khác: biển mây ở hai ngọn núi khác nhau, hoa nở ở hai tỉnh khác nhau.
Hai bài chỉ cùng đề tài (vũ trụ, khủng long, một giải đấu lớn như ASIAD) luôn là KHÁC câu chuyện. Phân vân → coi là KHÁC.

Tự kiểm tra: phải đặt được MỘT tên dạng "ai + làm gì + ở đâu/trận nào" đúng cho MỌI bài trong nhóm. Không đặt được → đó không phải cùng câu chuyện.

Ví dụ CÙNG câu chuyện: "Võ sĩ A hạ nhà vô địch thế giới, vào chung kết" và "A: từ chấn thương đến tấm huy chương bạc lịch sử"; "Học sinh Việt Nam giành 8 huy chương Olympic Hóa học" và "Nữ sinh Nam Định kể chuyện giành Vàng Olympic Hóa học"; "The Tiny Frog That Glows" và "Chú ếch tí hon phát sáng".
Ví dụ KHÁC câu chuyện: "Cầu thủ B lập cú đúp trước đội X" và "Cầu thủ B ghi siêu phẩm trước đội Y"; "Võ sĩ A vào chung kết ASIAD" và "Đội bóng chuyền giành vàng ASIAD"; "Tàu Curiosity chụp bình minh sao Hỏa" và "Kính Webb chụp tinh vân".

Cách làm: với mỗi câu chuyện xuất hiện từ 2 lần trở lên (giữa các bài MỚI với nhau, hoặc giữa bài MỚI và bài ĐÃ ĐĂNG), gọi tên câu chuyện trước, rồi mới ghi mã các bài kể nó. Đọc lại tiêu đề của từng mã trước khi ghi, để không ghi nhầm số.

ĐẦU RA: chỉ một JSON nén một dòng:
{"chuyen":[{"ten":"vo si A vao chung ket asiad","moi":["M1","M4"],"cu":["C12"]}]}
- "ten": tên câu chuyện NGẮN 3–7 chữ dạng ai + làm gì + ở đâu/trận nào, KHÔNG DẤU, giữ nguyên tên riêng có trong bài (tên người, nơi, loài, giải); không thêm chi tiết chỉ một bài có.
- "moi": mã các bài MỚI kể câu chuyện đó. "cu": mã các bài ĐÃ ĐĂNG kể câu chuyện đó (không có thì []).
- Chỉ ghi câu chuyện có từ 2 bài trở lên tính cả mới lẫn đã đăng, và có ít nhất 1 bài mới.
Không có gì trùng thì trả {"chuyen":[]}."""


def _published(day: str, days: int) -> list[str]:
    """Tiêu đề các bài đã đăng trong `days` ngày TRƯỚC `day` (kèm tiêu đề gốc của bài dịch,
    để bắt được cùng một bài TIME for Kids đăng lại cho khối lớp khác)."""
    start = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    out = []
    for p in sorted(ISSUES.glob("????-??-??.json")):
        if start <= p.stem < day:
            for a in read_json(p, {}).get("articles") or []:
                t = a.get("title", "")
                if a.get("title_original"):
                    t += f" ({a['title_original']})"
                if a.get("sapo"):                 # tiêu đề hai báo có khi khác hẳn nhau ("chim ồn nhất" / "tiếng như máy khoan")
                    t += " — " + a["sapo"][:100]
                out.append(t)
    return out


_STOP = {"va", "cua", "tai", "trong", "cho", "voi", "la", "co", "duoc", "mot", "nhung", "cac", "nguoi",
         "the", "tu", "den", "khi", "nay", "da", "se", "viet", "nam", "o", "ve", "ra", "len"}


def _words(s: str) -> set[str]:
    """Bỏ dấu, chữ thường → tập từ (để so tên câu chuyện không dấu với tiêu đề có dấu)."""
    s = unicodedata.normalize("NFD", (s or "").casefold()).replace("đ", "d")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return set(re.findall(r"[a-z0-9]{2,}", s)) - _STOP


def _ids(xs, prefix: str, n: int) -> list[int]:
    """["M3", "m 4", 5] → [2, 3, 4] (chỉ số 0-based hợp lệ). Model có thể bỏ tiền tố hoặc trả số."""
    out = []
    for x in xs if isinstance(xs, list) else [xs]:
        m = re.fullmatch(rf"\s*{prefix}?\s*(\d+)\s*", str(x), re.I)
        if m and 1 <= int(m.group(1)) <= n:
            out.append(int(m.group(1)) - 1)
    return out


def drop_repeats(cands: list[dict], cfg: dict, day: str) -> list[dict]:
    """Trả danh sách ứng viên đã bỏ bài trùng, giữ nguyên thứ tự."""
    days = int(cfg.get("review", {}).get("no_repeat_days", 7))
    old = _published(day, days)
    if not cands or (len(cands) < 2 and not old):      # không có gì để so → khỏi tốn một lần gọi AI
        return cands
    rows = [f"M{i}. {c['title']} — {(c.get('sapo') or '')[:160]}" for i, c in enumerate(cands, 1)]
    prompt = ("BÀI MỚI:\n" + "\n".join(rows)
              + f"\n\nĐÃ ĐĂNG {days} NGÀY QUA:\n" + ("\n".join(f"C{i}. {t}" for i, t in enumerate(old, 1)) or "(chưa có)")
              + '\n\nCHỈ TRẢ JSON nén một dòng {"chuyen":[{"ten":"..","moi":[..],"cu":[..]}]}. Không thêm chữ nào khác.')
    try:
        res = ask_json(prompt, system=SYSTEM, model=cfg["scoring"].get("model_dedup", "sonnet"))
    except Exception as e:
        log.error("Soát trùng lỗi, bỏ qua bước này: %s", e)
        return cands
    stories = res.get("chuyen") if isinstance(res, dict) else None
    if not isinstance(stories, list):
        log.error("Soát trùng: AI trả sai khuôn, bỏ qua bước này")
        return cands

    # Kiểm lại từng mã AI ghi: bài phải chứa một phần TÊN câu chuyện mà chính AI đặt, tính theo trọng số
    # chữ hiếm (tên riêng nặng, "giành", "2026" nhẹ). Đã gặp thật: AI bảo cụm "Olympic thiên văn" đã đăng
    # rồi trỏ sang bài về hố đen → cả câu chuyện suýt bị xóa. Đo 07/10: mã ghi nhầm kiểu đó khớp 0,0; bài
    # đúng thấp nhất 0,16 (bỏ dấu thì "Tâm" lẫn với "trung tâm" nên tên người Việt nhẹ ký). Chỉ là lưới
    # chặn lỗi THÔ: AI trỏ nhầm sang bài cùng đề tài (khớp tới ~0,5) thì không chặn được.
    df = Counter(w for t in rows + old for w in _words(t))
    idf = lambda w: math.log((len(rows) + len(old) + 1) / (df[w] + 1))

    def mentions(name: set[str], text: str) -> bool:
        total = sum(idf(w) for w in name)
        return total > 0 and sum(idf(w) for w in name & _words(text)) / total >= NAME_COVER

    n = len(cands)
    parent = list(range(n))                       # gộp nhóm bắc cầu: M1~M4 và M4~M7 → một nhóm

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen_before: dict[int, str] = {}
    names: dict[int, str] = {}
    for s in stories:
        if not isinstance(s, dict):
            continue
        name = _words(str(s.get("ten") or ""))
        if not name:
            continue
        ms_all, cs_all = _ids(s.get("moi") or [], "M", n), _ids(s.get("cu") or [], "C", len(old))
        ms = [m for m in ms_all if mentions(name, rows[m])]
        cs = [c for c in cs_all if mentions(name, old[c])]
        if len(ms) < len(ms_all) or len(cs) < len(cs_all):
            bad = [f"M{m + 1}" for m in ms_all if m not in ms] + [f"C{c + 1}" for c in cs_all if c not in cs]
            log.info("Soát trùng: bỏ qua mã AI nghi ghi nhầm %s (chuyện '%s')", ",".join(bad), s.get("ten"))
        for m in ms:
            names[m] = str(s.get("ten"))
        for m in ms[1:]:
            parent[root(m)] = root(ms[0])
        if cs:
            for m in ms:
                seen_before[m] = old[cs[0]]
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(i)

    # Bài tốt nhất mỗi nhóm: điểm cao nhất, rồi nhiều ảnh hơn, rồi bài tiếng Việt (khỏi dịch), rồi dài hơn
    best_key = lambda i: (cands[i].get("score") or 0, len(cands[i].get("images") or []),
                          cands[i].get("lang") != "en", cands[i].get("words") or 0)
    drop: dict[int, str] = {}
    for members in groups.values():
        hit = next((seen_before[m] for m in members if m in seen_before), None)
        if hit:                                   # cả nhóm kể lại chuyện đã đăng
            for m in members:
                drop[m] = "đã đăng: " + hit[:70]
        elif len(members) > 1:
            keep = max(members, key=best_key)
            for m in members:
                if m != keep:
                    drop[m] = "trùng: " + cands[keep]["title"][:70]
    if len(drop) > n * MAX_DROP_SHARE:
        log.warning("Soát trùng: AI đòi bỏ %d/%d bài — quá nhiều, nghi gộp nhầm theo đề tài, bỏ qua kết quả", len(drop), n)
        return cands
    for i, why in drop.items():
        log.info("Bỏ bài trùng [%s]: %s  ← %s", names.get(i, "?"), cands[i]["title"][:60], why)
    log.info("Soát trùng: bỏ %d/%d bài (%d trùng trong số, %d đã đăng %d ngày qua)", len(drop), n,
             sum(w.startswith("trùng") for w in drop.values()), sum(w.startswith("đã đăng") for w in drop.values()), days)
    return [c for i, c in enumerate(cands) if i not in drop]
