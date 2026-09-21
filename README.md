# Báo Tốt Lành

Tờ báo mỗi ngày dành cho trẻ em, do bố mẹ tự chạy. Mỗi sáng hệ thống thu thập tin từ các báo Việt Nam và
vài nguồn khoa học cho trẻ em quốc tế, lọc qua 4 tầng, viết lại theo đúng độ tuổi từng bé, rồi xuất một
số báo 6–8 bài. Con đọc trên máy tính bảng qua web app cài được, không cuộn vô tận, không link ra ngoài,
không quảng cáo.

## Cấu trúc

```
config/newspaper.yaml   ← HIẾN PHÁP: nguồn, từ cấm, tiêu chí, độ tuổi, sở thích. File duy nhất cần sửa.
pipeline/               ← 4 tầng lọc (Python)
  collect.py            tầng 1: RSS whitelist, khử trùng lặp
  rules.py              tầng 2: chặn từ khóa cứng (có dấu, theo ranh giới từ)
  score.py              tầng 3: AI (Haiku) chấm điểm 0–10 theo tiêu đề + mô tả
  rewrite.py            tầng 4: AI (Sonnet) đọc toàn văn, kiểm tra an toàn lần cuối, viết 2 bản + hoạt động
  build_issue.py        chọn bài cân bằng chuyên mục, xuất số báo
  run_daily.py          chạy tất cả
docs/                   ← web app (GitHub Pages phục vụ thư mục này)
  data/latest.json      số báo mới nhất; data/issues/YYYY-MM-DD.json các số cũ
data/review/            ← báo cáo cho cha mẹ: bài lên báo, hàng chờ, bị loại và lý do (không công khai)
scripts/run_daily.ps1   ← chạy + đẩy lên GitHub, Task Scheduler gọi mỗi sáng
scripts/register_task.ps1 ← đăng ký Task Scheduler (chạy một lần)
```

## Cài đặt lần đầu

1. Python 3.11+, Node 18+, Git.
2. `python -m venv .venv` rồi `.venv\Scripts\pip install -r pipeline\requirements.txt`
3. `npm install -g @anthropic-ai/claude-code` rồi `claude login` (dùng tài khoản Claude đang có, không cần API key).
4. Sửa `config/newspaper.yaml`: tên bé, tuổi, sở thích, chuyên mục.
5. Chạy thử: `.venv\Scripts\python pipeline\run_daily.py --dry-run` để xem AI chọn gì mà chưa viết lại.
6. Chạy thật: `.venv\Scripts\python pipeline\run_daily.py` → xem `docs/` bằng bất kỳ máy chủ tĩnh nào.
7. Tự động mỗi sáng: `powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1`

## Chi phí

AI chạy một lần mỗi ngày ở trung tâm, không phụ thuộc số người đọc. Qua Claude Code dùng gói cá nhân
đang có; nếu chuyển sang API thì khoảng 2–5 USD/tháng.

## Nguyên tắc thiết kế

- Lọc nhiều tầng, không tin một tầng nào. Tầng rẻ chạy trước, AI chỉ xem phần còn lại.
- Mỗi ngày một số báo hữu hạn. Đọc hết là hết.
- Không ảnh từ báo gốc, không link ra ngoài trong chế độ trẻ em.
- Mọi bài lên báo đều truy được nguồn và lý do trong Góc cha mẹ và `data/review/`.
- Mọi tiêu chí viết bằng tiếng Việt thường trong một file, bố mẹ tự sửa được.
