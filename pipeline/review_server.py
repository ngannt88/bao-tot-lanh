"""Máy chủ duyệt tại máy: phục vụ docs/ + API cho trang duyệt của cha mẹ.

  python pipeline/review_server.py            # http://localhost:8765/duyet.html
"""
from __future__ import annotations
import json, sys, threading, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, load_config, today_str, read_json, SITE_DATA, setup_logging
from candidates import load as load_candidates, CAND_IMG
from publish import publish

log = setup_logging()
PORT = 8765
DOCS = ROOT / "docs"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(DOCS), **kw)

    def log_message(self, fmt, *args):  # bớt ồn
        if "/api/" in (args[0] if args else ""):
            log.info("HTTP " + fmt, *args)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/candidates":
            day = q.get("date", [today_str()])[0]
            data = load_candidates(day)
            if not data:
                return self._json({"error": f"Chưa có ứng viên ngày {day}. Chạy pipeline trước."}, 404)
            issue = read_json(SITE_DATA / "issues" / f"{day}.json", None)
            data["published_ids"] = [a["id"] for a in issue["articles"]] if issue else []
            data["site_url"] = "https://ngannt88.github.io/bao-tot-lanh/"
            return self._json(data)
        if u.path == "/api/days":
            days = sorted([p.stem for p in (ROOT / "data" / "candidates").glob("????-??-??.json")], reverse=True)
            return self._json({"days": days})
        if u.path.startswith("/cand-img/"):
            # ảnh ứng viên chưa xuất bản, chỉ phục vụ tại máy
            rel = u.path[len("/cand-img/"):]
            f = (CAND_IMG / rel).resolve()
            if not str(f).startswith(str(CAND_IMG.resolve())) or not f.exists():
                self.send_error(404); return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(f.stat().st_size))
            self.end_headers()
            self.wfile.write(f.read_bytes())
            return
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "JSON hỏng"}, 400)
        if u.path == "/api/publish":
            ids = body.get("ids") or []
            day = body.get("date") or today_str()
            if not ids:
                return self._json({"error": "Chưa chọn bài nào"}, 400)
            try:
                res = publish(day, ids, load_config(), push=bool(body.get("push", True)))
                return self._json(res)
            except Exception as e:
                log.exception("publish lỗi")
                return self._json({"error": str(e)}, 500)
        if u.path == "/api/run":
            # chạy lại pipeline (khi cha mẹ bấm "Lấy tin mới")
            import subprocess
            def run():
                subprocess.run([sys.executable, str(ROOT / "pipeline" / "run_daily.py"), "--force"], cwd=ROOT)
            threading.Thread(target=run, daemon=True).start()
            return self._json({"ok": True, "message": "Đang chạy, tải lại trang sau 2–3 phút."})
        self.send_error(404)


def main():
    open_browser = "--open" in sys.argv
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log.info("Máy chủ duyệt: http://localhost:%d/duyet.html", PORT)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}/duyet.html")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
