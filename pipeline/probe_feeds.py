"""Dò thử danh sách RSS ứng viên: feed nào sống, bao nhiêu bài, bài mới nhất bao lâu."""
import sys, time, json, concurrent.futures as cf
import feedparser, requests

CANDIDATES = {
    # VnExpress
    "vnexpress/khoa-hoc": "https://vnexpress.net/rss/khoa-hoc.rss",
    "vnexpress/giao-duc": "https://vnexpress.net/rss/giao-duc.rss",
    "vnexpress/the-thao": "https://vnexpress.net/rss/the-thao.rss",
    "vnexpress/so-hoa": "https://vnexpress.net/rss/so-hoa.rss",
    "vnexpress/du-lich": "https://vnexpress.net/rss/du-lich.rss",
    "vnexpress/khoa-hoc-cong-nghe": "https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",
    # Tuổi Trẻ
    "tuoitre/giao-duc": "https://tuoitre.vn/rss/giao-duc.rss",
    "tuoitre/khoa-hoc": "https://tuoitre.vn/rss/khoa-hoc.rss",
    "tuoitre/the-thao": "https://tuoitre.vn/rss/the-thao.rss",
    "tuoitre/nhip-song-tre": "https://tuoitre.vn/rss/nhip-song-tre.rss",
    "tuoitre/van-hoa": "https://tuoitre.vn/rss/van-hoa.rss",
    "tuoitre/du-lich": "https://tuoitre.vn/rss/du-lich.rss",
    # Thanh Niên
    "thanhnien/giao-duc": "https://thanhnien.vn/rss/giao-duc.rss",
    "thanhnien/gioi-tre": "https://thanhnien.vn/rss/gioi-tre.rss",
    "thanhnien/cong-nghe": "https://thanhnien.vn/rss/cong-nghe.rss",
    "thanhnien/the-thao": "https://thanhnien.vn/rss/the-thao.rss",
    "thanhnien/van-hoa": "https://thanhnien.vn/rss/van-hoa.rss",
    # Dân Trí
    "dantri/giao-duc": "https://dantri.com.vn/rss/giao-duc.rss",
    "dantri/khoa-hoc": "https://dantri.com.vn/rss/khoa-hoc.rss",
    "dantri/khoa-hoc-cong-nghe": "https://dantri.com.vn/rss/khoa-hoc-cong-nghe.rss",
    "dantri/the-thao": "https://dantri.com.vn/rss/the-thao.rss",
    "dantri/du-lich": "https://dantri.com.vn/rss/du-lich.rss",
    # Tiền Phong
    "tienphong/giao-duc": "https://tienphong.vn/rss/giao-duc-71.rss",
    "tienphong/khoa-hoc": "https://tienphong.vn/rss/khoa-hoc-cong-nghe-40.rss",
    "tienphong/the-thao": "https://tienphong.vn/rss/the-thao-8.rss",
    # Lao Động
    "laodong/giao-duc": "https://laodong.vn/rss/giao-duc.rss",
    "laodong/the-thao": "https://laodong.vn/rss/the-thao.rss",
    "laodong/cong-nghe": "https://laodong.vn/rss/cong-nghe.rss",
    # VietnamPlus
    "vietnamplus/khoahoc": "https://www.vietnamplus.vn/rss/khoahoc.rss",
    "vietnamplus/giaoduc": "https://www.vietnamplus.vn/rss/giaoduc.rss",
    "vietnamplus/thethao": "https://www.vietnamplus.vn/rss/thethao.rss",
    # VTV
    "vtv/giao-duc": "https://vtv.vn/giao-duc.rss",
    "vtv/khoa-hoc": "https://vtv.vn/khoa-hoc-cong-nghe.rss",
    "vtv/the-thao": "https://vtv.vn/the-thao.rss",
    # Khoa học & Đời sống / khoahoc.tv / Thiếu niên
    "khoahocdoisong/rss": "https://khoahocdoisong.vn/rss/home.rss",
    "khoahoctv/rss": "https://khoahoc.tv/rss",
    "khoahoctv/feed": "https://khoahoc.tv/feed",
    "thieunien/rss": "https://thieunien.vn/rss/home.rss",
    "thieunien/feed": "https://thieunien.vn/feed",
    "nhandan/giao-duc": "https://nhandan.vn/rss/giao-duc-1200.rss",
    "nhandan/khoa-hoc": "https://nhandan.vn/rss/khoa-hoc-cong-nghe-1192.rss",
    "baotintuc/giao-duc": "https://baotintuc.vn/giao-duc.rss",
    "baotintuc/khoa-hoc": "https://baotintuc.vn/khoa-hoc-cong-nghe.rss",
    "vov/giao-duc": "https://vov.vn/rss/giao-duc-16.rss",
    "vov/khoa-hoc": "https://vov.vn/rss/khoa-hoc-cong-nghe-77.rss",
    "kienthuc/khoa-hoc": "https://kienthuc.net.vn/rss/khoa-hoc-cong-nghe-8.rss",
    "vietnamnet/giao-duc": "https://vietnamnet.vn/rss/giao-duc.rss",
    "vietnamnet/khoa-hoc": "https://vietnamnet.vn/rss/khoa-hoc.rss",
    "vietnamnet/the-thao": "https://vietnamnet.vn/rss/the-thao.rss",
    # Quốc tế cho trẻ (sẽ dịch)
    "intl/nasa": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "intl/snexplores": "https://www.snexplores.org/feed",
    "intl/dogonews": "https://www.dogonews.com/feeds/all.rss",
    "intl/bbc-newsround": "https://feeds.bbci.co.uk/newsround/rss.xml",
    "intl/smithsonian-science": "https://www.smithsonianmag.com/rss/science-nature/",
    "intl/phys-org": "https://phys.org/rss-feed/",
    "intl/natgeo-kids": "https://kids.nationalgeographic.com/feed",
    "intl/kidsnews-au": "https://www.kidsnews.com.au/rss",
    "intl/twn-kids": "https://theweek.com/feed/kids",
    "intl/sciencedaily-top": "https://www.sciencedaily.com/rss/top/science.xml",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SafeNewsKids/0.1"}

def probe(name, url):
    t0 = time.time()
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        status = r.status_code
        fp = feedparser.parse(r.content)
        n = len(fp.entries)
        newest = None
        for e in fp.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts:
                age_h = (time.time() - time.mktime(ts)) / 3600
                newest = age_h if newest is None else min(newest, age_h)
        has_desc = sum(1 for e in fp.entries if e.get("summary")) if n else 0
        has_img = sum(1 for e in fp.entries if ("media_content" in e or "enclosures" in e and e.enclosures or "<img" in (e.get("summary") or ""))) if n else 0
        return dict(name=name, url=url, status=status, items=n, newest_h=None if newest is None else round(newest, 1),
                    desc=has_desc, img=has_img, ms=int((time.time()-t0)*1000), err=None, title=fp.feed.get("title"))
    except Exception as ex:
        return dict(name=name, url=url, status=None, items=0, newest_h=None, desc=0, img=0, ms=int((time.time()-t0)*1000), err=str(ex)[:80], title=None)

def main():
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda kv: probe(*kv), CANDIDATES.items()))
    results.sort(key=lambda r: (r["items"] == 0, r["name"]))
    print(f"{'feed':32} {'http':>4} {'items':>5} {'newest_h':>8} {'desc':>4} {'img':>3}  note")
    for r in results:
        note = r["err"] or (r["title"] or "")[:40]
        print(f"{r['name']:32} {str(r['status']):>4} {r['items']:>5} {str(r['newest_h']):>8} {r['desc']:>4} {r['img']:>3}  {note}")
    ok = [r for r in results if r["items"] > 0]
    print(f"\nSống: {len(ok)}/{len(results)}")
    json.dump(results, open(sys.argv[1] if len(sys.argv) > 1 else "probe_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
