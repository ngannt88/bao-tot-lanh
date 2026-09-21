"""Tạo giọng đọc tiếng Việt cho từng bài trong số báo, kèm mốc thời gian theo câu.

Vì sao cần: bé 7 tuổi chưa đọc trôi. Nghe giọng thật và thấy câu đang đọc sáng lên
là cách trẻ tập đọc, thay vì bắt con tự dò từng chữ.

Sinh ra hai file cho mỗi bài, trong docs/data/audio/<ngày>/:
  <id>.mp3    giọng đọc cả bài
  <id>.json   {"dur": tổng giây, "cues": [{"t": giây bắt đầu, "p": chỉ số đoạn, "s": vị trí ký tự, "e": ...}]}

Chạy tự động sau khi xuất bản. Chạy tay:  python pipeline/tts.py --date 2026-09-22
"""
from __future__ import annotations
import asyncio, re, shutil, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import edge_tts
from common import setup_logging, write_json, read_json, SITE_DATA, ISSUES, today_str, load_config

log = setup_logging()
AUDIO = SITE_DATA / "audio"
VOICE = "vi-VN-HoaiMyNeural"
RATE = "-8%"          # chậm hơn một chút cho trẻ tập đọc
PARALLEL = 4
KEEP_DAYS = 3         # giữ audio bao nhiêu ngày gần nhất
MAX_CHARS = 9000      # bài dài hơn thì chỉ đọc phần đầu
TEXT_KINDS = ("p", "h", "q", "li")


def _pieces(article: dict) -> list[tuple[int, str]]:
    """Trả [(chỉ số đoạn trong blocks, văn bản)] theo đúng thứ tự đọc: tiêu đề, sapo, rồi thân bài."""
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


async def _synth(text: str, voice: str, rate: str) -> tuple[bytes, list[dict]]:
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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _map_cues(pieces: list[tuple[int, str]], cues: list[dict]) -> list[dict]:
    """Gán mỗi mốc câu vào đúng đoạn và vị trí ký tự, bằng cách dò tuần tự trên văn bản đã ghép."""
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
        if at < 0:                                   # dấu câu khác nhau → thử khớp 25 ký tự đầu
            at = joined.find(needle[:25], cursor)
        if at < 0:
            continue
        cursor = at + len(needle)
        for blk_i, s, e in spans:
            if s <= at < e:
                out.append({"t": c["t"], "p": blk_i, "s": at - s, "e": min(at - s + len(needle), e - s)})
                break
    return out


async def _one(article: dict, out_dir: Path, voice: str, rate: str) -> dict | None:
    pieces = _pieces(article)
    text = "\n".join(_norm(t) for _, t in pieces if t.strip())
    if len(text) < 40:
        return None
    try:
        audio, cues = await _synth(text, voice, rate)
    except Exception as e:
        log.warning("Giọng đọc lỗi (%s): %s", str(e)[:70], article["title"][:45])
        return None
    if not audio:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{article['id']}.mp3").write_bytes(audio)
    mapped = _map_cues(pieces, cues)
    dur = max((c["t"] + c.get("d", 0) for c in cues), default=0)
    write_json(out_dir / f"{article['id']}.json", {"dur": round(dur, 2), "cues": mapped})
    return {"id": article["id"], "kb": len(audio) // 1024, "cues": len(mapped), "dur": round(dur)}


async def _run(articles: list[dict], out_dir: Path, voice: str, rate: str) -> list[dict]:
    sem = asyncio.Semaphore(PARALLEL)

    async def guarded(a):
        async with sem:
            return await _one(a, out_dir, voice, rate)
    return [r for r in await asyncio.gather(*(guarded(a) for a in articles)) if r]


def cleanup(keep_days: int = KEEP_DAYS) -> int:
    """Xóa audio của các ngày cũ để kho không phình."""
    if not AUDIO.exists():
        return 0
    days = sorted([d for d in AUDIO.iterdir() if d.is_dir()], reverse=True)
    removed = 0
    for d in days[keep_days:]:
        shutil.rmtree(d, ignore_errors=True)
        removed += 1
    return removed


def build(day: str | None = None, cfg: dict | None = None) -> dict:
    """Tạo giọng đọc cho toàn bộ bài của số báo ngày đó. Trả thống kê."""
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
    todo = [a for a in issue["articles"][:limit] if not (out_dir / f"{a['id']}.mp3").exists()]
    if not todo:
        return {"day": day, "made": 0, "note": "đã có đủ"}
    t0 = time.time()
    res = asyncio.run(_run(todo, out_dir, tc.get("voice", VOICE), tc.get("rate", RATE)))
    removed = cleanup(int(tc.get("keep_days", KEEP_DAYS)))
    mb = sum(r["kb"] for r in res) / 1024
    log.info("Giọng đọc %s: %d/%d bài, %.1f MB, %.0fs (xóa %d ngày cũ)",
             day, len(res), len(todo), mb, time.time() - t0, removed)
    return {"day": day, "made": len(res), "failed": len(todo) - len(res),
            "mb": round(mb, 1), "secs": round(time.time() - t0), "removed_days": removed}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today_str())
    a = ap.parse_args()
    print(build(a.date))
