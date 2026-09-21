# Báo Tốt Lành

Tờ báo mỗi ngày dành cho trẻ em, do bố mẹ tự chạy và tự duyệt. Mỗi sáng hệ thống thu tin từ các báo
Việt Nam, lọc qua 3 tầng (nguồn, từ khóa, AI chấm điểm), tách **nguyên văn** 10–12 bài ứng viên kèm ảnh
gốc và chú thích. Bố mẹ mở trang duyệt, chọn 6–8 bài, bấm Xuất bản. Con đọc trên máy tính bảng qua web
app: đúng bài báo thật, đúng ảnh, đúng lời nhà báo, nhưng không quảng cáo, không tin liên quan, không
bình luận, không link ra ngoài, không cuộn vô tận.

## Luồng mỗi sáng

```
6:00 hoặc khi đăng nhập Windows
  → pipeline/run_daily.py   thu RSS → chặn từ khóa → AI chấm → chọn ứng viên → tách nguyên văn + ảnh
  → review_server.py        mở http://localhost:8765/duyet.html
  → bố mẹ chọn bài, bấm Xuất bản   → docs/data/… được ghi và đẩy lên GitHub Pages
  → con mở app trên máy tính bảng  https://ngannt88.github.io/bao-tot-lanh/
```

## Cấu trúc

```
config/newspaper.yaml     ← HIẾN PHÁP: nguồn, từ cấm, tiêu chí AI, chuyên mục. File duy nhất cần sửa.
pipeline/
  collect.py              tầng 1: RSS whitelist, khử trùng lặp, nhớ bài đã thấy
  rules.py                tầng 2: chặn từ khóa (có dấu, theo ranh giới từ)
  score.py                tầng 3: AI (Haiku) chấm 0–10 theo tiêu đề + mô tả; không có AI vẫn chạy được
  candidates.py           chọn ứng viên cân bằng chuyên mục
  extract.py              tách nguyên văn: tiêu đề, sapo, tác giả, ảnh + chú thích, đoạn (theo từng báo)
  publish.py              ghi số báo, chép ảnh, commit + push
  review_server.py        máy chủ tại máy: docs/ + API duyệt
  run_daily.py            chạy tất cả
docs/                     ← web app (GitHub Pages phục vụ thư mục này)
  index.html app.js app.css sw.js   app của con
  duyet.html              trang duyệt của bố mẹ (chỉ hoạt động khi chạy review_server tại máy)
  data/latest.json, data/issues/, data/img/   số báo đã duyệt và ảnh
data/candidates/          ← ứng viên chưa duyệt (không công khai, không đưa lên git)
scripts/run_daily.ps1     ← Task Scheduler gọi; scripts/register_task.ps1 đăng ký (chạy một lần)
```

## Cài đặt lần đầu

1. Python 3.11+, Node 18+, Git, tài khoản GitHub (đăng nhập `gh auth login`).
2. `python -m venv .venv` rồi `.venv\Scripts\pip install -r pipeline\requirements.txt`
3. `npm install -g @anthropic-ai/claude-code` rồi `claude login` (dùng tài khoản Claude đang có, không cần API key).
   Không đăng nhập thì hệ thống vẫn chạy, chỉ thiếu điểm AI, bố mẹ phải đọc kỹ hơn khi duyệt.
4. Sửa `config/newspaper.yaml` theo ý gia đình.
5. Chạy thử: `.venv\Scripts\python pipeline\run_daily.py` rồi `.venv\Scripts\python pipeline\review_server.py --open`
6. Tự động mỗi sáng: `powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1`

## Nguyên tắc

- Nguyên văn bài, không nguyên trang: giữ đúng lời nhà báo và ảnh, bỏ mọi thứ ngoài bài.
- Không có gì lên báo mà bố mẹ chưa bấm chọn.
- Lọc nhiều tầng, tầng rẻ chạy trước; AI chỉ chấm điểm, không viết gì.
- Mỗi ngày một số báo hữu hạn. Đọc hết là hết.
- Mọi bài truy được nguồn trong Góc cha mẹ. Bản quyền thuộc báo gốc; dùng trong gia đình.
