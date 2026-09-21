"""Dùng chung: đường dẫn, cấu hình, log, chuẩn hóa chữ."""
from __future__ import annotations
import json, logging, re, unicodedata, hashlib, html
from datetime import datetime, timezone, timedelta
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "newspaper.yaml"
DATA = ROOT / "data"
RAW = DATA / "raw"            # bài thu về mỗi ngày
STATE = DATA / "state.json"   # url đã thấy, để không lặp
LOGS = DATA / "logs"
SITE_DATA = ROOT / "docs" / "data"   # GitHub Pages phục vụ thư mục docs/
ISSUES = SITE_DATA / "issues"
REVIEW = DATA / "review"      # hàng chờ cha mẹ duyệt
for p in (RAW, LOGS, ISSUES, REVIEW):
    p.mkdir(parents=True, exist_ok=True)

VN_TZ = timezone(timedelta(hours=7))


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def today_str() -> str:
    return now_vn().strftime("%Y-%m-%d")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(name: str = "pipeline") -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname).1s %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    fh = logging.FileHandler(LOGS / f"{today_str()}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(sh)
    log.addHandler(fh)
    return log


def read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)          # &ocirc; → ô, &amp; → &
    s = _TAG.sub(" ", s)
    s = html.unescape(s).replace(" ", " ")
    return _WS.sub(" ", s).strip()


def norm(s: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng – dùng để so khớp."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return _WS.sub(" ", s.lower()).strip()


def slug(s: str, n: int = 60) -> str:
    s = norm(s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-") or "bai"


def article_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def word_count(s: str) -> int:
    return len((s or "").split())


# ---- Tải HTTP có dự phòng khi báo cấu hình chứng chỉ sai (lỗi bên họ, thường tạm thời) ----
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_INSECURE_HOSTS: set[str] = set()


def http_get(url: str, headers: dict, timeout: int = 20) -> "requests.Response":
    """GET bình thường; nếu lỗi chứng chỉ thì thử lại KHÔNG xác minh và ghi cảnh báo một lần mỗi host.
    Chấp nhận được vì đây là tin công khai, còn qua lọc từ khóa, AI và cha mẹ duyệt."""
    host = url.split("/")[2] if "//" in url else url
    if host in _INSECURE_HOSTS:
        return requests.get(url, headers=headers, timeout=timeout, verify=False)
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.SSLError:
        logging.getLogger("pipeline").warning("Chứng chỉ lỗi ở %s → tải không xác minh (lỗi cấu hình bên báo)", host)
        _INSECURE_HOSTS.add(host)
        return requests.get(url, headers=headers, timeout=timeout, verify=False)
