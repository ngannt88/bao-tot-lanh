"""Tạo giọng đọc tiếng Việt cho từng bài trong số báo.

Vì sao cần: bé 7 tuổi chưa đọc trôi. Nghe giọng thật và thấy đoạn đang đọc sáng lên
là cách trẻ tập đọc, thay vì bắt con tự dò từng chữ.

Hai bộ giọng, chọn trong config `audio.engine`:
  gtts      giọng nữ Google Dịch (quen thuộc). Không báo được vị trí đang đọc, nên
            mỗi ĐOẠN được cắt thành một file riêng; app phát nối tiếp và làm sáng
            đúng đoạn đang phát.
  edge      giọng Microsoft vi-VN. Một file cho cả bài, kèm mốc theo từng câu.
Nếu bộ chính lỗi (Google chặn vì gọi nhiều) thì tự lùi về bộ còn lại.

Sinh ra trong docs/data/audio/<ngày>/:
  <id>.json   {"engine": .., "dur": giây, "parts": [{"p": chỉ số đoạn, "f": tên file, "dur": giây}]}
              hoặc với edge: {"engine":"edge","dur":.., "cues":[{"t","p","s","e"}]}
  <id>.mp3            (edge) hoặc
  <id>-0.mp3, ...     (gtts, mỗi đoạn một file)

Chạy tay:  python pipeline/tts.py --date 2026-09-22
"""
from __future__ import annotations
import asyncio, io, re, shutil, sys, time
import concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import setup_logging, write_json, read_json, SITE_DATA, ISSUES, today_str, load_config

log = setup_logging()
AUDIO = SITE_DATA / "audio"
VOICE = "vi-VN-HoaiMyNeural"
RATE = "-8%"
PARALLEL = 4
KEEP_DAYS = 3
MAX_CHARS = 9000
TEXT_KINDS = ("p", "h", "q", "li")
MP3_FRAME = 26            # ~26 ms mỗi khung mp3 24 kHz, dùng để đo thời lượng


def _pieces(article: dict) -> list[tuple[int, str]]:
    """[(chỉ số đoạn trong blocks, văn bản)] theo thứ tự đọc: tiêu đề (-2), sapo (-1), rồi thân bài."""
    out: list[tuple[int, str]] = [(-2, article.get("title", ""))]
    if article.get("sapo"):
        out.append((-1, article["sapo"]))
    total = sum(len(t) for _, t in out)
    for i, b in enumerate(article.get("blocks", [])):
        if b.get("t") in TEXT_KINDS and b.get("text"):
            if total > MAX_CHARS:
                break
            out.append((i, b["text"]))
            total += len(b["text"])
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# Bảng bitrate và tần số của mp3 Layer III, để đo thời lượng không cần thư viện ngoài.
_BR_V1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_BR_V2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _mp3_seconds(data: bytes) -> float:
    """Đo thời lượng mp3 bằng cách đi qua từng khung.

    Đã trả giá: trước đây ước theo kích thước tệp (32 kbps). gTTS thực ra trả mp3
    nặng hơn nhiều, nên thời lượng bị tính dài gấp hơn ba lần và vạch tiến độ trong
    app gần như không nhích (hết bài mới tới 29%). Đếm khung thì chính xác.
    """
    i, n, total = 0, len(data), 0.0
    if data[:3] == b"ID3" and n > 10:            # bỏ qua thẻ ID3v2 ở đầu tệp
        i = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14
                  | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    while i < n - 3:
        if data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        ver = (data[i + 1] >> 3) & 3             # 3 = MPEG1, 2 = MPEG2, 0 = MPEG2.5
        layer = (data[i + 1] >> 1) & 3           # 1 = Layer III
        br_i, sr_i = (data[i + 2] >> 4) & 0xF, (data[i + 2] >> 2) & 3
        if ver == 1 or layer != 1 or sr_i == 3 or br_i in (0, 15):
            i += 1
            continue
        br = (_BR_V1 if ver == 3 else _BR_V2)[br_i] * 1000
        sr, spf = _SR[ver][sr_i], (1152 if ver == 3 else 576)
        length = spf // 8 * br // sr + ((data[i + 2] >> 1) & 1)
        if length < 24:
            i += 1
            continue
        total += spf / sr
        i += length
    return total if total > 0 else max(1.0, n / 13600)   # tệp lạ: ước theo byte


# --------------------------------------------------------------------------- gTTS
def _gtts_one(text: str, tries: int = 3) -> bytes | None:
    from gtts import gTTS
    for k in range(tries):
        try:
            b = io.BytesIO()
            gTTS(_norm(text), lang="vi").write_to_fp(b)
            return b.getvalue()
        except Exception as e:
            if k == tries - 1:
                log.warning("gTTS lỗi: %s", str(e)[:90])
            time.sleep(1.5 * (k + 1))
    return None


def _build_gtts(article: dict, out_dir: Path) -> dict | None:
    pieces = [(i, t) for i, t in _pieces(article) if t.strip()]
    if not pieces:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(max_workers=3) as ex:     # 3 luồng: nhanh mà không dồn dập
        blobs = list(ex.map(lambda p: _gtts_one(p[1]), pieces))
    if sum(1 for b in blobs if b) < len(pieces) * 0.8:   # hỏng quá nhiều → coi như thất bại
        return None
    parts, total, kb = [], 0.0, 0
    for (blk_i, _), blob in zip(pieces, blobs):
        if not blob:
            continue
        fname = f"{article['id']}-{len(parts)}.mp3"
        (out_dir / fname).write_bytes(blob)
        dur = _mp3_seconds(blob)
        parts.append({"p": blk_i, "f": fname, "dur": round(dur, 2)})
        total += dur
        kb += len(blob) // 1024
    if not parts:
        return None
    write_json(out_dir / f"{article['id']}.json",
               {"engine": "gtts", "dur": round(total, 2), "parts": parts})
    return {"id": article["id"], "kb": kb, "parts": len(parts), "dur": round(total)}


# --------------------------------------------------------------------------- edge-tts
async def _edge_synth(text: str, voice: str, rate: str) -> tuple[bytes, list[dict]]:
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate)
    audio, cues = bytearray(), []
    async for ch in comm.stream():
        if ch["type"] == "audio":
            audio.extend(ch["data"])
        elif ch["type"] in ("SentenceBoundary", "WordBoundary"):
            cues.append({"t": round(ch["offset"] / 1e7, 2),
                         "d": round(ch.get("duration", 0) / 1e7, 2),
                         "text": ch.get("text", "")})
    return bytes(audio), cues


def _map_cues(pieces: list[tuple[int, str]], cues: list[dict]) -> list[dict]:
    joined, spans, pos = "", [], 0
    for blk_i, text in pieces:
        t = _norm(text)
        spans.append((blk_i, pos, pos + len(t)))
        joined += t + " "
        pos += len(t) + 1
    out, cursor = [], 0
    for c in cues:
        needle = _norm(c.get("text", ""))
        if not needle:
            continue
        at = joined.find(needle, cursor)
        if at < 0:
            at = joined.find(needle[:25], cursor)
        if at < 0:
            continue
        cursor = at + len(needle)
        for blk_i, s, e in spans:
            if s <= at < e:
                out.append({"t": c["t"], "p": blk_i, "s": at - s, "e": min(at - s + len(needle), e - s)})
                break
    return out


async def _build_edge_one(article: dict, out_dir: Path, voice: str, rate: str) -> dict | None:
    pieces = _pieces(article)
    text = "\n".join(_norm(t) for _, t in pieces if t.strip())
    if len(text) < 40:
        return None
    # Máy chủ giọng Microsoft thỉnh thoảng từ chối một lần rồi lại nhận (NoAudioReceived).
    # Không thử lại thì bài đó mất giọng hẳn, mà đây lại là bộ giọng DỰ PHÒNG — hỏng nốt
    # là cả số báo không có tiếng. gTTS đã thử 3 lần, chỗ này trước đây không lần nào.
    audio, cues = b"", []
    for k in range(3):
        try:
            audio, cues = await _edge_synth(text, voice, rate)
            if audio:
                break
        except Exception as e:
            if k == 2:
                log.warning("edge-tts lỗi (%s): %s", str(e)[:60], article["title"][:40])
        await asyncio.sleep(1.5 * (k + 1))
    if not audio:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{article['id']}.mp3").write_bytes(audio)
    dur = max((c["t"] + c.get("d", 0) for c in cues), default=0)
    write_json(out_dir / f"{article['id']}.json",
               {"engine": "edge", "dur": round(dur, 2), "cues": _map_cues(pieces, cues)})
    return {"id": article["id"], "kb": len(audio) // 1024, "dur": round(dur)}


async def _run_edge(articles: list[dict], out_dir: Path, voice: str, rate: str) -> list[dict]:
    sem = asyncio.Semaphore(PARALLEL)

    async def guarded(a):
        async with sem:
            return await _build_edge_one(a, out_dir, voice, rate)
    return [r for r in await asyncio.gather(*(guarded(a) for a in articles)) if r]


# --------------------------------------------------------------------------- chung
def _prune_orphans(out_dir: Path, keep_ids: set[str]) -> int:
    """Xóa tệp giọng của những bài KHÔNG còn trong số báo.

    Vì sao cần: cha mẹ duyệt lại, đổi bài, hay chạy lại pipeline thì bài cũ rời số
    báo nhưng mp3 vẫn nằm trong thư mục và vẫn bị đẩy lên web. Đã có ngày dư 14 tệp
    không ai nghe, nặng hơn 30 MB.
    """
    if not out_dir.exists():
        return 0
    n = 0
    for f in out_dir.iterdir():
        if f.is_file() and f.stem.split("-")[0] not in keep_ids:
            f.unlink(missing_ok=True)
            n += 1
    if n:
        log.info("Xóa %d tệp giọng của bài không còn trong số báo", n)
    return n


def cleanup(keep_days: int = KEEP_DAYS) -> int:
    if not AUDIO.exists():
        return 0
    days = sorted([d for d in AUDIO.iterdir() if d.is_dir()], reverse=True)
    removed = 0
    for d in days[keep_days:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed


def build(day: str | None = None, cfg: dict | None = None) -> dict:
    day = day or today_str()
    cfg = cfg or load_config()
    tc = cfg.get("audio", {})
    if not tc.get("enabled", True):
        return {"skipped": "audio.enabled = false"}
    issue = read_json(ISSUES / f"{day}.json", None)
    if not issue:
        return {"error": f"chưa có số báo {day}"}
    out_dir = AUDIO / day
    limit = int(tc.get("max_articles", 10))
    keep_days = int(tc.get("keep_days", KEEP_DAYS))
    # Giữ giọng của MỌI bài còn trong số báo, không chỉ 10 bài đầu: max_articles giới hạn
    # việc TẠO thêm, không phải lý do xóa tệp đang dùng tốt.
    orphans = _prune_orphans(out_dir, {a["id"] for a in issue["articles"]})
    todo = [a for a in issue["articles"][:limit] if not (out_dir / f"{a['id']}.json").exists()]
    if not todo:
        # vẫn phải dọn: trước đây thoát sớm ở đây nên ngày cũ không bao giờ bị xóa
        return {"day": day, "made": 0, "note": "đã có đủ", "orphans": orphans,
                "removed_days": cleanup(keep_days)}

    engine = tc.get("engine", "gtts")
    t0 = time.time()
    res: list[dict] = []
    if engine == "gtts":
        with cf.ThreadPoolExecutor(max_workers=2) as ex:      # 2 bài cùng lúc, mỗi bài 3 đoạn
            res = [r for r in ex.map(lambda a: _build_gtts(a, out_dir), todo) if r]
        if len(res) < len(todo) * 0.6:                        # Google chặn → lùi về edge-tts
            log.warning("Giọng Google chỉ làm được %d/%d bài, chuyển sang giọng dự phòng", len(res), len(todo))
            rest = [a for a in todo if not (out_dir / f"{a['id']}.json").exists()]
            res += asyncio.run(_run_edge(rest, out_dir, tc.get("voice", VOICE), tc.get("rate", RATE)))
    else:
        res = asyncio.run(_run_edge(todo, out_dir, tc.get("voice", VOICE), tc.get("rate", RATE)))

    removed = cleanup(keep_days)
    mb = sum(r["kb"] for r in res) / 1024
    log.info("Giọng đọc %s (%s): %d/%d bài, %.1f MB, %.0fs (xóa %d ngày cũ)",
             day, engine, len(res), len(todo), mb, time.time() - t0, removed)
    return {"day": day, "engine": engine, "made": len(res), "failed": len(todo) - len(res),
            "mb": round(mb, 1), "secs": round(time.time() - t0), "removed_days": removed,
            "orphans": orphans}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today_str())
    ap.add_argument("--engine", default=None, help="gtts hoặc edge")
    a = ap.parse_args()
    cfg = load_config()
    if a.engine:
        cfg.setdefault("audio", {})["engine"] = a.engine
    print(build(a.date, cfg))
