# LEVEL UP

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

## Bài tiếng Anh được dịch

Báo Việt không phải lúc nào cũng có bài hay cho trẻ, nên hệ thống lấy thêm từ các nguồn tiếng Anh viết
cho trẻ em và các tạp chí khoa học, rồi **dịch sát** sang tiếng Việt: giữ đúng số đoạn, đúng ảnh và chú
thích, không tóm tắt, không thêm bài học. Mỗi bài dịch hiện nhãn "Dịch từ <nguồn>" và góc cha mẹ vẫn giữ
link bài gốc. Tối đa `translate.max_per_issue` bài mỗi số, phần còn lại là báo Việt nguyên văn.

Nguồn tiếng Anh đang dùng: TIME for Kids, Science News Explores (chung + vũ trụ, động vật, công nghệ),
Curious Kids của The Conversation, NASA, ScienceAlert, IEEE Spectrum, MIT Technology Review, Smithsonian.
BBC Newsround và New Scientist đã tắt vì không truy cập được từ Việt Nam.

Nguồn tiếng Anh dùng **bộ chặn từ khóa riêng** (`blocklist_en`), vì nhiều từ trùng mặt chữ mà khác nghĩa,
ví dụ "game" trong tiếng Việt là trò chơi điện tử còn trong tiếng Anh là trận đấu.

## AI dùng bao nhiêu

AI chỉ chấm điểm, không viết gì, chạy hai vòng bằng Haiku:

| Vòng | Đọc gì | Suy nghĩ ẩn | Đo thật |
|---|---|---|---|
| 1. Chấm thô | tiêu đề + mô tả, 40 bài/lần | tắt | 40 bài ≈ 1.200 token ra, 24 giây |
| 2. Kiểm ứng viên | 1.200 chữ đầu bài, 8 bài/lần | tối đa 2.000 | 23 bài ≈ 4.500 token ra, 26 giây |
| 3. Dịch (Sonnet) | toàn bài tiếng Anh, 1 bài/lần | tắt | 1 bài ≈ 3.300 token ra, 48 giây |

Ngày thường 150–250 bài mới → khoảng **10.000 token đầu ra Haiku mỗi ngày, 1–2 phút**, chạy lúc 6:00.
So với một buổi code dùng Opus (hàng triệu token) thì không đáng kể. Nếu bật suy nghĩ ở vòng 1 sẽ tốn gấp 9 lần
mà chỉ tinh hơn chút; vòng 2 mới là nơi đáng để AI suy nghĩ vì chỉ 25 bài và có nội dung thật.

## Giọng đọc thật, chữ sáng theo lời

Bé 7 tuổi chưa đọc trôi, nên mỗi sáng `pipeline/tts.py` tạo sẵn file giọng đọc tiếng Việt cho các bài đầu
số báo, kèm mốc thời gian theo từng câu. Trong app, nút **Nghe đọc bài này** phát giọng và làm **sáng câu
đang đọc**, cuộn theo. Đây là cách trẻ tập đọc: nghe và nhìn chữ cùng lúc.

| | |
|---|---|
| Công cụ | edge-tts, giọng `vi-VN-HoaiMyNeural`, chậm 8% |
| Đo thật | 10 bài mất 153 giây, 15,7 MB |
| Giới hạn | `audio.max_articles` bài mỗi số, giữ `audio.keep_days` ngày |
| Token AI | 0 |

Bài ngoài hạn mức vẫn nghe được bằng giọng máy của trình duyệt, chỉ là không có chữ sáng theo.
File mp3 **không** được đưa vào bộ nhớ đệm của app, tránh làm đầy máy tính bảng.

## Con thích bài nào

Cuối mỗi bài có nút 👍. Dữ liệu này **chỉ nằm trên máy tính bảng**, không gửi đi đâu. Góc cha mẹ hiển thị
số bài đã đọc, chủ đề con thích nhất và danh sách bài được thích, kèm nút sao chép báo cáo.

**Hệ thống không tự đọc được tín hiệu này**, vì nó nằm trên máy của con chứ không phải máy chạy pipeline.
Muốn biến nó thành thay đổi thật, cha mẹ sao chép báo cáo rồi sửa `scoring.criteria` hoặc `max_per_issue`
trong `config/newspaper.yaml`. Góc cha mẹ ghi rõ điều này để không hứa hẹn sai với trẻ.

## Lưới an toàn: tự xuất bản

Nếu đến giờ hẹn (`review.auto_publish.hour`, mặc định 7:30) mà bố mẹ chưa duyệt, hệ thống tự chọn
các bài AI chấm từ `min_score` (mặc định 8/10) trở lên, cân bằng chuyên mục, và xuất bản. Bố mẹ vẫn
có thể mở trang duyệt sửa lại sau. **Không có điểm AI thì không tự xuất bản**, nên bắt buộc đã
`claude login`. Tắt bằng `enabled: false` rồi chạy lại `register_task.ps1`.

## Web nằm ở nhánh `gh-pages`, kho không phình

Mỗi lần xuất bản, thư mục `docs/` (kể cả ảnh) được chụp thành **một commit không lịch sử** và đẩy ghi đè lên nhánh
`gh-pages`; GitHub Pages phục vụ nhánh này. Nhánh `main` chỉ giữ mã nguồn và JSON số báo (ảnh nằm trong
`.gitignore`), nên kho không lớn theo ngày dù mỗi ngày thêm vài MB ảnh.

## Ba tác vụ Task Scheduler

| Tác vụ | Khi nào | Làm gì |
|---|---|---|
| BaoTotLanh-HangNgay | 6:00, và khi đăng nhập Windows | lấy tin, lọc, tách ứng viên, mở trang duyệt, báo Windows |
| BaoTotLanh-TuXuatBan | giờ hẹn, và 12 phút sau đăng nhập | chưa duyệt → tự xuất bản bài điểm cao |
| BaoTotLanh-KiemTra | thứ hai 7:00 | kiểm tra feed và bộ tách từng báo, báo nếu hỏng |

## Nguồn không có RSS

Trong `config/newspaper.yaml`, nguồn có `type: html` sẽ lấy link bài từ trang chuyên mục theo
`link_pattern` (regex). Dùng cho báo trẻ em như Thiếu niên Tiền phong. Trang chậm hay lỗi thì hôm đó
thiếu nguồn, không ảnh hưởng nguồn khác.

## Lưu ý Windows

Các file `scripts/*.ps1` phải lưu **UTF-8 có BOM**: Windows PowerShell 5.1 đọc UTF-8 không BOM thành ANSI, chữ Việt
biến thành dấu nháy cong và kịch bản lỗi cú pháp ngay khi Task Scheduler gọi (đã gặp, đã sửa). Log ghi bằng
`Add-Content -Encoding UTF8`.

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
