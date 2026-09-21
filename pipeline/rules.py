"""TẦNG 2 — Chặn từ khóa cứng. Rẻ, tức thì, loại phần lớn rác trước khi tốn AI."""
from __future__ import annotations
import re
import unicodedata
from common import setup_logging

log = setup_logging()


_WS = re.compile(r"\s+")


def vnorm(s: str) -> str:
    """Chữ thường, GIỮ DẤU (tiếng Việt có thanh điệu, bỏ dấu sẽ bắt nhầm), gộp khoảng trắng."""
    return _WS.sub(" ", unicodedata.normalize("NFC", s or "").casefold()).strip()


class RuleFilter:
    def __init__(self, cfg: dict):
        self.groups: dict[str, list[tuple[str, re.Pattern]]] = {}
        for group, words in (cfg.get("blocklist") or {}).items():
            pats = []
            for w in words:
                n = vnorm(w)
                if not n:
                    continue
                # khớp nguyên từ/cụm từ theo ranh giới chữ Unicode (\w hiểu chữ có dấu)
                pat = re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)")
                pats.append((w, pat))
            self.groups[group] = pats
        self.exceptions = [vnorm(x) for x in cfg.get("blocklist_exceptions") or []]

    def check(self, title: str, summary: str = "") -> tuple[bool, list[str]]:
        """Trả (bị_chặn, [lý do]). Tiêu đề nặng hơn mô tả: mô tả chỉ chặn nhóm 'nặng'."""
        t = vnorm(title)
        s = vnorm(summary)
        for ex in self.exceptions:
            if ex in t:
                t = t.replace(ex, " ")
        hits = []
        for group, pats in self.groups.items():
            for raw, pat in pats:
                if pat.search(t):
                    hits.append(f"{group}:{raw}")
                elif group in HEAVY and pat.search(s):
                    hits.append(f"{group}:{raw}(mô tả)")
        return (len(hits) > 0, hits)


# Nhóm "nặng": xuất hiện trong mô tả cũng loại. Nhóm nhẹ chỉ xét tiêu đề (tránh loại nhầm).
HEAVY = {"bao-luc-tai-nan", "nguoi-lon", "kinh-di", "te-nan", "chinh-tri-phap-luat"}


def apply_rules(articles: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    rf = RuleFilter(cfg)
    passed, blocked = [], []
    for a in articles:
        hit, why = rf.check(a["title"], a.get("summary", ""))
        if hit:
            a = dict(a, rejected_by="rules", reject_reasons=why)
            blocked.append(a)
        else:
            passed.append(a)
    log.info("Tầng 2: %d qua, %d bị chặn", len(passed), len(blocked))
    return passed, blocked
