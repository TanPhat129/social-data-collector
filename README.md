# Social Tutor Lead Collection

Thu thập các bài đăng **tìm gia sư** từ những nhóm Facebook mà tài khoản đã
được phép xem, lọc nhu cầu, trích xuất thông tin lead và ghi vào Google Sheets.

> Dự án dùng Browser Connector với phiên đăng nhập do người dùng tự tạo. Không
> tự động nhập mật khẩu, xử lý CAPTCHA/checkpoint hoặc vượt qua quyền truy cập
> của Facebook.

## Luồng hoạt động

```text
config/sources.yaml hoặc Odoo
        ↓
Facebook Browser Connector / Graph API
        ↓
Raw post → lọc keyword → phân loại nhu cầu → trích xuất → kiểm tra dữ liệu
        ↓
SQLite chống trùng → Google Sheets
```

Mặc định, dự án dùng Browser Connector và danh sách nhóm trong
`config/sources.yaml`. Khi cấu hình đủ Odoo, danh sách nguồn sẽ được đồng bộ từ
Odoo thay cho YAML.

## Trạng thái hiện tại

- Có thể tạo profile Playwright riêng theo Facebook UID và dùng lại session.
- Có 3 collector: `facebook_browser`, `facebook_graph` và `mock`.
- Bộ lọc deterministic xử lý các cụm như `cần/tìm gia sư`, `cần tìm gs`,
  `tìm giáo viên`; có thể thay bằng OpenAI qua `AI_PROVIDER=openai`.
- SQLite chỉ đánh dấu bài đã xử lý **sau khi** writer nhận batch lead.
- Google Sheets ghi theo 13 cột: `STT, Group, Subject, Platform, Grade,
  Location, Mode, Budget, Phone, Content, URL, Posted At, Collected At`.
  `STT` được tạo tự động bằng công thức Sheets.
- Facebook thay đổi DOM thường xuyên. Browser Connector hiện chỉ lấy phần nội
  dung bài đăng khi tìm được card/post-message phù hợp; hãy luôn chạy
  `--debug` và kiểm tra URL trước khi dùng kết quả vận hành.

## Cài đặt

Yêu cầu: Python 3.11+ và Chromium cho Playwright.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Trên macOS/Linux, kích hoạt môi trường bằng `source .venv/bin/activate`.

## Cấu hình tối thiểu: Browser Connector

Mở `.env` và cấu hình tối thiểu như sau:

```dotenv
COLLECTOR_PROVIDER=facebook_browser
SOURCE_CONFIG_PATH=config/sources.yaml
FACEBOOK_BROWSER_PROFILE_ROOT=.secrets/facebook-profiles
FACEBOOK_BROWSER_ACCOUNT_UID=<facebook_numeric_uid>
FACEBOOK_BROWSER_HEADLESS=true
FACEBOOK_BROWSER_MAX_SCROLLS=2
DATABASE_URL=sqlite:///./data/social_tutor.db
KEYWORDS_PATH=config/keywords.yaml
```

Đặt UID số của tài khoản Facebook vào cả `.env` và
`config/sources.yaml > defaults > allowed_account_uids`. Không đặt mật khẩu,
cookie, mã 2FA hay token vào YAML hoặc Git.

Sửa `config/sources.yaml` để chỉ chứa các nhóm được phép thu thập. Mỗi nguồn
cần có `id`, `name` và `source_url`. Sửa `config/keywords.yaml` để thêm/bớt
cụm từ tạo candidate; keyword chỉ là bước lọc đầu, chưa khẳng định đó là lead.

## Đăng nhập Facebook một lần cho mỗi UID

Chạy lệnh sau trong terminal:

```powershell
python -m scripts.login_facebook
```

Trình duyệt hiển thị sẽ dùng thư mục profile
`.secrets/facebook-profiles/<UID>`. Người dùng tự đăng nhập và hoàn tất mọi
checkpoint, sau đó quay lại terminal nhấn Enter. Chương trình kiểm tra cookie
`c_user` có đúng UID đã cấu hình rồi mới giữ profile.

Có thể dùng entry point tương đương:

```powershell
python -m app.main --prepare-facebook-profile
```

Nếu Facebook yêu cầu login/checkpoint lại, chạy lại bước này. Không xóa thư mục
profile nếu muốn giữ session; thư mục này đã được `.gitignore`.

## Chạy thu thập

Chạy một lượt:

```powershell
python -m app.main
```

Chạy và xem quyết định cho từng bài:

```powershell
python -m app.main --debug
```

Các lý do bỏ qua thường gặp:

| Log | Ý nghĩa |
| --- | --- |
| `keyword_no_match` | Nội dung post không có keyword trong cấu hình. |
| `intent_OTHER` | Có keyword nhưng được nhận diện là bài chào dạy/không phải tìm gia sư. |
| `already_processed` | `post_id` hoặc hash nội dung đã được ghi trong SQLite. |
| `duplicate_in_batch` | Nội dung trùng với một post khác ngay trong lượt đang chạy. |
| `validation` | Thiếu trường bắt buộc hoặc confidence không đạt ngưỡng. |

Với `--debug`, log có `post_url` và preview nội dung để đối chiếu. Nếu log cho
thấy `extracted_posts=0`, collector chưa nhận diện được card bài viết của giao
diện Facebook hiện tại; kiểm tra `logs/facebook_dom_debug.*` (nếu đã tạo) và
đừng coi lượt chạy đó là không có bài mới.

Chạy theo lịch:

```powershell
python -m app.main --schedule
```

Chu kỳ lấy từ `COLLECTION_INTERVAL_MINUTES` (phút). Lệnh chạy ngay một lượt
trước khi bắt đầu scheduler.

## Google Sheets

Điền hai biến sau vào `.env`:

```dotenv
GOOGLE_SHEET_ID=<spreadsheet_id>
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
```

Chia sẻ spreadsheet cho email của service account với quyền Editor. Sheet đầu
tiên phải có hàng tiêu đề đúng thứ tự sau:

```text
STT | Group | Subject | Platform | Grade | Location | Mode | Budget | Phone | Content | URL | Posted At | Collected At
```

Writer tìm dòng đầu tiên trống ở các cột `Group` đến `Collected At`; vì vậy
format hoặc công thức STT còn sót lại không làm lead mới bị ghi quá xa phía
dưới. Mỗi dòng mới đặt `=ROW()-1` ở cột STT. Nếu thiếu cấu hình Google Sheets,
lead chỉ được log là `accepted locally` và **không** được gửi lên Sheet.

## AI, Graph API và Odoo (tùy chọn)

### OpenAI

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=<api_key>
OPENAI_MODEL=gpt-5-mini
AI_MAX_RETRIES=3
```

Không có API key, dùng `AI_PROVIDER=deterministic` (mặc định).

### Facebook Graph API

```dotenv
COLLECTOR_PROVIDER=facebook_graph
FACEBOOK_ACCESS_TOKEN=<access_token>
FACEBOOK_GRAPH_API_VERSION=v22.0
FACEBOOK_MAX_POSTS_PER_SOURCE=100
```

Chỉ dùng token có quyền hợp lệ với đúng nguồn Facebook. Cấu hình này không cần
Browser Connector.

### Odoo

```dotenv
ODOO_URL=https://<host>
ODOO_DB=<database>
ODOO_USERNAME=<username>
ODOO_PASSWORD=<password>
ODOO_SOURCE_MODEL=social.tutor.source
ODOO_SOURCE_NAME_FIELD=name
ODOO_SOURCE_PLATFORM_FIELD=platform
ODOO_SOURCE_EXTERNAL_ID_FIELD=facebook_group_id
ODOO_SOURCE_ENABLED_FIELD=enabled
```

Khi đủ bốn thông tin kết nối Odoo, ứng dụng dùng model/field trên để lấy các
source được bật. Xác minh tên model và field trong Odoo trước khi vận hành.

## Cấu trúc mã nguồn hiện tại

> Đây là cây thư mục đang có trong repository. Cấu trúc Clean Architecture đề
> xuất (`infrastructure/`, `domain/models.py`, `use_cases/pipeline.py`) chưa
> được tách/migrate theo đúng tên đó, nên không nên dùng nó làm đường dẫn import
> hoặc hướng dẫn sửa code lúc này.

```text
social-tutor-system/
├── app/
│   ├── config.py                 # Đọc .env bằng Pydantic Settings
│   ├── main.py                   # Entry point: python -m app.main
│   ├── schemas.py                # Source, RawPost, TutorLead
│   ├── pipeline.py               # Keyword → classifier → extractor → validator → writer
│   ├── source_config.py          # Đọc allow-list sources.yaml
│   ├── core/
│   │   └── container.py          # Dependency wiring
│   ├── collectors/
│   │   ├── base.py               # BaseCollector
│   │   ├── facebook_browser.py   # Playwright Browser Connector
│   │   ├── facebook_graph.py
│   │   └── mock.py
│   ├── processing/               # keyword filter, classifier, extractor, validator
│   ├── integrations/             # Google Sheets writer, OpenAI adapter
│   ├── database/
│   │   └── processed_posts.py    # SQLite chống trùng
│   ├── odoo/                     # JSON-RPC client và source service
│   ├── use_cases/                # collect_posts, process_leads, sync_config
│   ├── presentation/             # CLI, Facebook profile auth, scheduler entry
│   ├── scheduler/                # APScheduler job và scheduler factory
│   └── domain/                   # Package placeholder, chưa chứa models/interfaces thực thi
├── config/                       # sources.yaml, keywords.yaml
├── data/                         # SQLite runtime (được gitignore)
├── logs/                         # Log/DOM debug runtime (được gitignore)
├── scripts/                      # login_facebook.py, inspect_facebook_dom.py
├── .secrets/                     # Playwright profiles (được gitignore)
├── IDEA.md                       # Ý tưởng, trạng thái và roadmap cập nhật
├── Idea.pdf                      # Tài liệu gốc
├── .env.example
├── .gitignore
└── requirements.txt
```

`app/domain/models/` và `app/domain/interfaces/` hiện chỉ là package trống.
Models thực tế nằm ở `app/schemas.py`; abstraction collector nằm tại
`app/collectors/base.py`. Nếu muốn chuyển hẳn sang cấu trúc đề xuất, cần làm một
refactor riêng để đổi import và bổ sung regression test, không chỉ đổi tên thư
mục.

## Dữ liệu cục bộ và chống trùng

SQLite tại `DATABASE_URL` giữ `post_id` và hash nội dung đã gửi thành công qua
writer. Để crawl lại một bài cụ thể, chỉ xóa bản ghi tương ứng trong database;
không xóa toàn bộ database trừ khi thực sự muốn chạy lại mọi bài đã có.

`.env`, `.secrets/`, `data/`, `logs/` và service-account key đã nằm trong
`.gitignore`. Không commit các dữ liệu này.

## Kiểm thử

```powershell
python -m pytest -q -p no:cacheprovider
```

Các kiểm thử không xác nhận được phiên Facebook, Google Sheets, OpenAI hoặc
Odoo thật vì các dịch vụ đó cần credential riêng.

## GitHub: các lệnh commit cơ bản

Repository chính: <https://github.com/TanPhat129/social-data-collector>

Kiểm tra thay đổi trước khi commit:

```powershell
git status
git diff
```

Chạy test, thêm các file đã chọn và tạo commit:

```powershell
python -m pytest -q -p no:cacheprovider
git add README.md app/ tests/
git commit -m "Mô tả ngắn gọn thay đổi"
```

Đẩy commit lên nhánh `main`:

```powershell
git push origin main
```
### $\color{red}{\text{Lưu ý không tự push code vào nhánh main, hãy tạo một branch riêng rồi push code để doublecheck.}}$ Trước khi bắt đầu một thay đổi mới, lấy cập nhật mới nhất để tránh xung đột:

```powershell
git pull --rebase origin main
```

Để thêm toàn bộ thay đổi mã nguồn đã xem xét, có thể dùng `git add -A`, sau đó
chạy lại `git status` trước khi commit. Tuyệt đối không dùng `git add -f` cho
`.env`, `.secrets/`, `data/`, `logs/`, service-account key hoặc file export
lead; các file này đã được `.gitignore` loại trừ.

## Checklist triển khai

| Hạng mục | Hiện trạng | Việc cần làm trước production |
| --- | --- | --- |
| Môi trường và biến cấu hình | Có `.env.example` cho Odoo, Google Sheets, Facebook, OpenAI, SQLite và scheduler. | Tạo `.env` riêng từ mẫu, điền credential thật và không commit file này. |
| Database local | `ProcessedPostStore` tự tạo bảng `processed_posts` và index khi khởi động. Không có migration script hay `models.py` dùng cho SQLite. | Sao lưu `data/social_tutor.db`; chỉ cần migration riêng nếu schema sẽ phát triển thêm. |
| Kết nối Odoo | Có unit test dùng `FakeOdooClient` để kiểm tra mapping model/field. | Xác nhận model/field thật và chạy smoke test với Odoo staging/production có quyền đọc. |
| Google Sheets | Có unit test kiểm tra mapping 13 cột và dòng trống; chưa gọi Google API thật. | Chia sẻ Sheet cho service account, điền hai biến Google và chạy một lead mẫu để kiểm tra quyền ghi. |
| Collector và pipeline | Có Mock collector, test keyword/classifier/extractor/pipeline và Browser/Graph collector không dùng mạng. | Test bằng dữ liệu post đã được phép sử dụng; chạy `--debug` để xác nhận Browser Connector đang lấy **post body**, không phải comment. |
| Scheduler | APScheduler đã chạy theo `COLLECTION_INTERVAL_MINUTES`, đồng thời chạy ngay một lượt khi khởi động. | Chạy thử tiến trình dài hạn và giám sát lỗi/overlap theo nhu cầu vận hành. |
| Logging | Log hiện in ra console; script debug Facebook có thể tạo artifact trong `logs/`. Chưa có `FileHandler` ghi log chạy ứng dụng vào `logs/` tự động. | Nếu cần log file tập trung, bổ sung `FileHandler`/rotating log và chính sách lưu giữ log. |

### Trình tự triển khai đề xuất

1. Tạo virtual environment, cài dependency và Chromium như phần **Cài đặt**.
2. Tạo `.env` từ `.env.example`; cấu hình Browser Connector và đăng nhập profile
   Facebook thủ công.
3. Kiểm tra `sources.yaml`, keyword và chạy `python -m app.main --debug`.
4. Cấu hình Google Sheet, chạy một lead mẫu và xác nhận đúng hàng/cột/STT.
5. Cấu hình Odoo, OpenAI hoặc Graph API chỉ sau khi smoke test credential thật
   trên môi trường được phép.
6. Bật `--schedule` sau khi Browser Connector và Google Sheets đã được xác nhận
   hoạt động; bổ sung file logging nếu cần theo dõi dài hạn.
