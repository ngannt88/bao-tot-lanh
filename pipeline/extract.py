"""Tách NGUYÊN VĂN bài báo: tiêu đề, sapo, tác giả, ảnh gốc + chú thích, thân bài theo đoạn.
Không sửa một chữ. Chỉ bỏ những gì nằm ngoài bài (quảng cáo, tin liên quan, bình luận, chia sẻ)."""
from __future__ import annotations
import io, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image
from common import setup_logging, word_count, strip_html, http_get

log = setup_logging()
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
           "Accept-Language": "vi,en;q=0.8"}
MAX_IMAGES = 12
MAX_TEXT_CHARS = 14000
MIN_WORDS = 80
IMG_MAX_W = 1280
IMG_MIN_SIDE = 220

# Khung chứa bài + sapo + tác giả theo từng báo. Không khớp thì rơi về readability.
SITE_RULES = {
    "vnexpress.net":   {"body": ["article.fck_detail"], "sapo": ["p.description"], "author": ["p.author_mail strong", "p.Normal[style*='text-align:right'] strong"]},
    "tuoitre.vn":      {"body": ["div.detail-content"], "sapo": ["h2.detail-sapo"], "author": ["div.author-info a.name", ".detail-author .name"]},
    "thanhnien.vn":    {"body": ["div.detail__content", "div.detail-content", "div.detail__cmain-main"], "sapo": ["div.detail__summary", "h2.detail-sapo"], "author": ["div.detail__author a", ".detail-author a"]},
    "dantri.com.vn":   {"body": ["div.singular-content", "div.e-magazine__body", "div.dt-news__content"], "sapo": ["h2.singular-sapo", "div.e-magazine__sapo"], "author": ["div.author-name a", ".author-wrap .author-name"]},
    "vietnamnet.vn":   {"body": ["div#maincontent", "div.maincontent"], "sapo": ["h2.content-detail-sapo", ".sapo"], "author": [".article-detail-author__info .name", "span.name a"]},
    "vietnamplus.vn":  {"body": ["div.article__body"], "sapo": ["div.article__sapo", "h2.article__sapo"], "author": ["div.article__author", ".article__meta .author"]},
    "tienphong.vn":    {"body": ["div.article__body"], "sapo": ["div.article__sapo", "h2.article__sapo"], "author": ["div.article__author", ".article__meta .author"]},
    "kienthuc.net.vn": {"body": ["div.article__body", "div.detail-content"], "sapo": ["div.article__sapo"], "author": []},
    "snexplores.org":  {"body": ["div.rich-text", "article .entry-content"], "sapo": [".single__deck", ".post__deck"], "author": [".byline__author a", ".byline a"]},
    "nasa.gov":        {"body": ["div.entry-content", "article .usa-prose"], "sapo": [], "author": []},
    "sciencedaily.com": {"body": ["div#text", "div#story_text"], "sapo": ["p.lead", "h1 + p"], "author": []},
    "smithsonianmag.com": {"body": ["div.article-body", "div.articleBody"], "sapo": [".subtitle", "h2.subtitle"], "author": [".author-name a", ".byline a"]},
    "bbc.co.uk":       {"body": ["article", "main"], "sapo": [], "author": []},
}
NOISE_SELECTORS = [
    "script", "style", "noscript", "iframe", "ins", "svg", "button", "form", "video", "audio",
    "[class*='related']", "[class*='lienquan']", "[class*='lien-quan']", "[id*='related']",
    "[class*='box-tinkhac']", "[class*='tinkhac']", "[class*='share']", "[class*='social']",
    "[class*='banner']", "[class*='advert']", "[class*='quangcao']", "[class*='sponsor']",
    "[class*='comment']", "[class*='binhluan']", "[class*='tag']", "[class*='footer']",
    "[type='RelatedOneNews']", "[type='RelatedNewsBox']", "[type='SubTitle']",
    ".VCSortableInPreviewMode[type='wrapnote']", ".box-taitro", ".embed-container", ".read-more", ".xem-them",
]
NOISE_TEXT = re.compile(r"^(xem thêm|đọc thêm|xem video|video:|theo dõi|mời bạn đọc|tin liên quan|ảnh:|nguồn:|>>|→)", re.I)
FILENAME_LIKE = re.compile(r"\.(jpe?g|png|gif|webp)\b|^ảnh \d+\.?$|- ảnh \d+\.?$|^image\d*$|^\d{6,}", re.I)


def _domain(url: str) -> str:
    h = urlparse(url).hostname or ""
    return h[4:] if h.startswith("www.") else h


def _rules(url: str) -> dict:
    d = _domain(url)
    for k, v in SITE_RULES.items():
        if d == k or d.endswith("." + k):
            return v
    return {"body": [], "sapo": [], "author": []}


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for s in selectors:
        el = soup.select_one(s)
        if el:
            t = el.get_text(" ", strip=True)
            if t:
                return t
    return ""


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for n in names:
        el = soup.find("meta", property=n) or soup.find("meta", attrs={"name": n})
        if el and el.get("content"):
            return el["content"].strip()
    return ""


def _img_url(img: Tag, base: str) -> str | None:
    for attr in ("data-original", "data-src", "data-lazy-src", "data-srcset", "srcset", "src"):
        v = img.get(attr)
        if not v:
            continue
        v = v.strip()
        if attr.endswith("srcset"):
            parts = [p.strip().split(" ")[0] for p in v.split(",") if p.strip()]
            v = parts[-1] if parts else ""
        if not v or v.startswith("data:"):
            continue
        return urljoin(base, v)
    return None


def _caption(fig: Tag | None, img: Tag) -> str:
    if fig is not None:
        fc = fig.find("figcaption") or fig.select_one(".PhotoCMS_Caption, .caption, .image__caption, .fig-caption, p.Image")
        if fc:
            t = fc.get_text(" ", strip=True)
            if t:
                return t
    alt = (img.get("alt") or img.get("title") or "").strip()
    if alt and not FILENAME_LIKE.search(alt) and len(alt) > 12:
        return alt
    return ""


def _download_image(url: str, dest: Path) -> tuple[int, int] | None:
    try:
        r = http_get(url, HEADERS, 25)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content))
        im.load()
        if getattr(im, "is_animated", False):
            return None
        if min(im.size) < IMG_MIN_SIDE:
            return None
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > IMG_MAX_W:
            im = im.resize((IMG_MAX_W, int(im.height * IMG_MAX_W / im.width)), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=82, optimize=True, progressive=True)
        return im.size
    except Exception as e:
        log.debug("Ảnh lỗi %s: %s", url[:60], str(e)[:60])
        return None


def _body_container(soup: BeautifulSoup, html: bytes, rules: dict) -> Tag | None:
    for s in rules.get("body", []):
        el = soup.select_one(s)
        if el and len(el.find_all("p")) >= 3:
            return el
    try:
        from readability import Document
        doc = Document(html)
        return BeautifulSoup(doc.summary(html_partial=True), "lxml")
    except Exception as e:
        log.warning("readability lỗi: %s", e)
        return None


def extract_article(a: dict, img_dir: Path) -> dict:
    """Trả về bản sao của a với: title, sapo, author, images[], blocks[], words, extracted_ok."""
    out = dict(a)
    try:
        r = http_get(a["url"], HEADERS, 25)
        r.raise_for_status()
        html = r.content
        base = r.url
    except Exception as e:
        out.update(extracted_ok=False, extract_error=f"tải trang lỗi: {str(e)[:80]}")
        return out
    soup = BeautifulSoup(html, "lxml")
    rules = _rules(base)

    h1 = soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else "") or _meta(soup, "og:title") or a["title"]
    sapo = _first_text(soup, rules.get("sapo", [])) or _meta(soup, "description", "og:description") or a.get("summary", "")
    author = _first_text(soup, rules.get("author", [])) or _meta(soup, "author", "article:author")
    author = re.sub(r"\s+", " ", author)[:80]
    if re.search(r"\.(vn|com|net|org)|^https?:", author, re.I) or author.lower() in ("admin", "ban biên tập"):
        author = ""
    og_image = _meta(soup, "og:image")

    body = _body_container(soup, html, rules)
    if body is None:
        out.update(extracted_ok=False, extract_error="không tìm được thân bài")
        return out
    for sel in NOISE_SELECTORS:
        try:
            for el in body.select(sel):
                el.decompose()
        except Exception:
            pass

    blocks: list[dict] = []
    images: list[dict] = []
    seen_img: set[str] = set()
    text_chars = 0

    def add_image(url: str | None, caption: str) -> None:
        if not url or url in seen_img or len(images) >= MAX_IMAGES:
            return
        seen_img.add(url)
        n = len(images)
        fname = f"{a['id']}-{n}.jpg"
        size = _download_image(url, img_dir / fname)
        if not size:
            return
        images.append({"file": fname, "caption": caption, "w": size[0], "h": size[1], "src_url": url})
        blocks.append({"t": "img", "i": len(images) - 1})

    handled = ("figure", "blockquote", "li")
    for el in body.find_all(["p", "h2", "h3", "figure", "img", "blockquote", "li", "table"]):
        if not isinstance(el, Tag):
            continue
        # bỏ phần tử nằm trong phần tử đã xử lý nguyên khối
        if el.name != "figure" and el.find_parent(handled):
            if not (el.name == "img" and el.find_parent("figure") is None):
                continue
        if el.name == "table":
            continue
        if el.name == "figure":
            img = el.find("img")
            if img is not None:
                add_image(_img_url(img, base), _caption(el, img))
            continue
        if el.name == "img":
            add_image(_img_url(el, base), _caption(None, el))
            continue
        # p / h2 / h3 / blockquote / li
        if el.name == "p" and el.find("img") is not None and len(el.get_text(strip=True)) < 5:
            img = el.find("img")
            add_image(_img_url(img, base), _caption(el.parent if el.parent else None, img))
            continue
        text = el.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if not text or NOISE_TEXT.match(text) or len(text) < 2:
            continue
        if text_chars + len(text) > MAX_TEXT_CHARS:
            break
        kind = {"p": "p", "h2": "h", "h3": "h", "blockquote": "q", "li": "li"}[el.name]
        if kind == "p" and blocks and blocks[-1]["t"] == "p" and blocks[-1]["text"] == text:
            continue
        blocks.append({"t": kind, "text": text})
        text_chars += len(text)

    # ảnh đại diện (og:image) đưa lên đầu nếu chưa có trong bài
    if og_image and urljoin(base, og_image) not in seen_img and len(images) < MAX_IMAGES:
        url = urljoin(base, og_image)
        fname = f"{a['id']}-lead.jpg"
        size = _download_image(url, img_dir / fname)
        if size:
            images.insert(0, {"file": fname, "caption": "", "w": size[0], "h": size[1], "src_url": url})
            for b in blocks:
                if b["t"] == "img":
                    b["i"] += 1
            seen_img.add(url)

    words = sum(word_count(b.get("text", "")) for b in blocks)
    # bỏ dòng tác giả lặp cuối bài nếu trùng
    if blocks and blocks[-1]["t"] == "p" and author and blocks[-1]["text"].strip() == author.strip():
        blocks.pop()
    out.update(title=title, sapo=strip_html(sapo)[:600], author=author, images=images, blocks=blocks,
               words=words, lead_image=(0 if images else None),
               extracted_ok=(words >= MIN_WORDS), extract_error=None if words >= MIN_WORDS else f"chỉ {words} chữ")
    return out
