# Ý tưởng & phạm vi hiện tại

## Mục tiêu

Xây dựng một công cụ hỗ trợ đội vận hành phát hiện nhanh bài đăng có nhu cầu
**tìm gia sư**, chuẩn hóa thông tin cơ bản và chuyển lead vào Google Sheets để
theo dõi. Công cụ không thay thế người kiểm duyệt: URL bài đăng và nội dung gốc
luôn được giữ để đối chiếu trước khi liên hệ.

## Người dùng và đầu ra

- Người vận hành cấu hình những nhóm Facebook mà tài khoản của họ được phép
  xem, keyword và Google Sheet đích.
- Hệ thống tạo một dòng lead gồm STT, nhóm, môn, lớp, khu vực, hình thức học,
  ngân sách, số điện thoại (nếu có), nội dung, URL và thời gian thu thập.
- Người vận hành mở URL, xác nhận lead và xử lý nghiệp vụ ở hệ thống nội bộ.

## Luồng nghiệp vụ

1. Nạp nguồn đang bật từ `config/sources.yaml`; khi Odoo đã cấu hình đầy đủ,
   nạp từ Odoo.
2. Browser Connector dùng profile Playwright riêng theo UID để đọc các group
   đã allow-list. Không tự động đăng nhập hoặc vượt checkpoint.
3. Chỉ lấy nội dung thân bài post, không dùng comment làm nội dung lead.
4. Keyword lọc candidate; classifier quyết định intent `FIND_TUTOR` hay
   `OTHER`.
5. Extractor lấy các trường có thể nhận biết bằng quy tắc hoặc AI.
6. Validator kiểm tra dữ liệu tối thiểu, SQLite chống trùng, sau đó writer ghi
   Google Sheets và đánh dấu post đã xử lý.

## Kiến trúc

```text
Nguồn cho phép
   └─ Facebook Browser / Graph API / Mock
          └─ LeadPipeline
              ├─ KeywordFilter
              ├─ IntentClassifier
              ├─ LeadExtractor + Validator
              ├─ ProcessedPostStore (SQLite)
              └─ GoogleSheetsWriter
```

Các adapter được nối trong `app/core/container.py`, giúp thay đổi collector,
AI provider hoặc nguồn cấu hình mà không đổi pipeline lõi.

## Điều đã có

- Profile Facebook persistent theo UID và kiểm tra UID của session.
- Allow-list URL Facebook và cấu hình 8 group mẫu.
- Debug log nêu URL post và nguyên nhân bài bị bỏ qua.
- Chống trùng trong batch và giữa các lượt chạy.
- Google Sheets theo đúng 13 cột, tự đánh STT và điền dòng trống đầu tiên.
- Scheduler định kỳ, deterministic processor và OpenAI adapter tùy chọn.

## Rủi ro và nguyên tắc vận hành

- DOM Facebook không ổn định: selector phải được kiểm thử lại khi
  `extracted_posts=0`; không suy diễn comment là nội dung post.
- Chỉ thu thập dữ liệu mà tài khoản có quyền xem và tuân thủ điều khoản nền
  tảng/quy định bảo vệ dữ liệu.
- Không lưu mật khẩu, cookie, token, API key hay service-account key trong Git.
- Keyword/classifier có thể sai. Luôn review URL và nội dung trước khi liên hệ.

## Roadmap thực tế

1. Ổn định selector Browser Connector bằng mẫu DOM/screenshot mới nhất và thêm
   regression test cho post card thực tế.
2. Bổ sung số liệu vận hành: số post đọc được, candidate, accepted, bị trùng và
   lỗi ghi Sheet cho mỗi source.
3. Đánh giá deterministic classifier bằng dữ liệu đã duyệt, rồi mới bật
   OpenAI/Odoo/Graph API trong production.
4. Thêm trạng thái review và người phụ trách ở hệ thống CRM/Odoo thay vì dùng
   Google Sheets như nguồn dữ liệu chính lâu dài.

`Idea.pdf` là tài liệu gốc được giữ nguyên. Tài liệu này là bản Markdown cập
nhật, dễ chỉnh sửa và phản ánh code/config hiện tại.
