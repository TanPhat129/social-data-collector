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
- Google Sheets ghi theo 14 cột: `STT, Group, Subject, Platform, Grade,
  Location, Mode, Budget, Phone, Content, URL, Author URL, Posted At, Collected At`.
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
STT | Group | Subject | Platform | Grade | Location | Mode | Budget | Phone | Content | URL | Author URL | Posted At | Collected At
```

Writer tìm dòng đầu tiên trống ở các cột `Group` đến `Collected At`; vì vậy
format hoặc công thức STT còn sót lại không làm lead mới bị ghi quá xa phía
dưới. Mỗi dòng mới đặt `=ROW()-1` ở cột STT. Nếu thiếu cấu hình Google Sheets,
lead chỉ được log là `accepted locally` và **không** được gửi lên Sheet.

`Posted At` lấy từ metadata thời gian của Facebook khi DOM/API cung cấp; `Author
URL` chỉ được ghi khi collector xác định được link profile của người tạo post.
Hai trường có thể để trống nếu Facebook không công khai metadata đó hoặc DOM
không đủ tin cậy, thay vì lấy nhầm link của comment.
Với post trong group, Facebook có thể chỉ cung cấp URL thành viên dạng
`/groups/<group-id>/user/<uid>/`; Browser Connector mở URL này trong tab phụ để
lấy URL profile cuối cùng, hoặc giữ URL thành viên nếu Facebook không redirect.
Khi Facebook chỉ hiện thời gian tương đối như `21 giờ`, Browser Connector quy
đổi thành `Collected At - 21 giờ`; đây là thời gian ước lượng tại lúc crawl.
Khi hover nhãn thời gian trả về tooltip ngày–giờ đầy đủ, tooltip đó được ưu
tiên để ghi `Posted At` chính xác.
Timestamp được xuất theo mẫu `YYYY-MM-DD HH:MM:SS` (ví dụ
`2026-09-21 14:08:10`).

`URL` bài viết là trường **bắt buộc**: lead thiếu permalink post sẽ bị validator
loại và không ghi Google Sheets. `Author URL` là trường tùy chọn; để trống là
hợp lệ đối với post ẩn danh hoặc khi Facebook không cung cấp link người đăng.
Với post ẩn danh, connector nhận diện nhãn `Người tham gia ẩn danh` ở header và
luôn để trống `Author URL`; link của comment không bao giờ được dùng thay thế.

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

Tạo nhánh riêng và đẩy lên để review (không push trực tiếp vào `main`):

```powershell
git switch -c feature/<mo-ta-ngan>
git push -u origin feature/<mo-ta-ngan>
```

Trước khi bắt đầu một thay đổi mới, lấy cập nhật mới nhất để tránh xung đột:

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
| Google Sheets | Có unit test kiểm tra mapping 14 cột và dòng trống; chưa gọi Google API thật. | Thêm cột `Author URL` vào Sheet, chia sẻ cho service account, điền hai biến Google và chạy một lead mẫu để kiểm tra quyền ghi. |
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

## Điều phối nhiều account tập trung (PostgreSQL)

Chỉ chuyển sang chế độ này sau khi luồng Browser Connector một account đã ổn
định. Chế độ mới thay SQLite chống trùng cục bộ bằng PostgreSQL dùng chung và
đưa Google Sheets vào outbox, không để browser worker ghi Sheet trực tiếp.

```text
account pool YAML -> shard barrier -> một browser worker / account
                                      -> PostgreSQL claim bài viết duy nhất
                                      -> transaction lead + sheet_outbox
                                      -> một Google Sheets writer tuần tự
```

Nguồn cấu hình do vận hành quản trị:

- `config/account_pools.yaml`: pool, account, đường dẫn profile, group được
  phép đọc và assignment group/account/shard. Copy từ
  `config/account_pools.example.yaml`; không commit file đã điền.
- PostgreSQL: trạng thái động account (`AVAILABLE`, `IN_USE`,
  `NEEDS_MANUAL_ACTION`, `DISABLED`), chống trùng toàn hệ thống, lead và
  `sheet_outbox`. Đồng bộ YAML không ghi đè trạng thái đang vận hành.

Với pilot 10 account × 50 group, gán 10 group/account cho mỗi shard `1` đến
`5`. Một round chạy song song các account ở shard 1, đợi toàn bộ shard kết
thúc/timeout, nghỉ 30–60 giây rồi sang shard 2. Không dùng scheduler khoảng
thời gian cố định nên không tạo lượt chạy chồng nhau. `max_concurrent_accounts`
giới hạn số account đồng thời trong mỗi shard.

### Khởi tạo và chạy một central round

```powershell
Copy-Item config/account_pools.example.yaml config/account_pools.yaml
# Chỉ khai báo profile/group mà đúng account có quyền xem.
python -m scripts.init_postgres
python -m app.main --orchestrate --pool pilot_hcm --debug
```

Thiết lập `.env` trước khi chạy:

```dotenv
POSTGRES_DSN=postgresql://<user>:<password>@<host>:5432/<database>
ACCOUNT_POOLS_PATH=config/account_pools.yaml
GOOGLE_SHEET_ID=<sheet_id>
GOOGLE_SERVICE_ACCOUNT_FILE=.secrets/google-service-account.json
SHEET_OUTBOX_BATCH_SIZE=50
```

`POSTGRES_DSN`, Google Sheet và profile browser khớp với từng account được bật
là bắt buộc trong chế độ này. `canonical_post_url` là bắt buộc trước khi claim;
`author_url` là tùy chọn và để trống cho bài ẩn danh. Khi hai account thấy cùng
một bài, PostgreSQL chỉ nhận claim đầu tiên theo
`(platform, canonical_post_url)`, vì vậy outbox chỉ tạo một dòng Sheet.

- `AVAILABLE`: có thể được phân công; shard đổi trạng thái atomically sang
  `IN_USE`.
- `IN_USE`: đang bị một worker khóa, không được worker khác sử dụng.
- `NEEDS_MANUAL_ACTION`: cần người vận hành kiểm tra login/checkpoint/quyền
  xem/lỗi worker; scheduler không tự dùng lại.
- `DISABLED`: người vận hành chủ động loại khỏi lịch chạy.

Lệnh trên chạy đúng một round hoàn chỉnh. Dùng supervisor bên ngoài để gọi
round tiếp theo sau khi tiến trình thoát và đã qua cooldown mong muốn; như vậy
vẫn giữ shard barrier và không mở trùng browser profile.

`pool` là chi tiết nội bộ và không hiện trong menu khi account discovery chỉ
thuộc một pool. `max_concurrent_accounts: 5` nghĩa là nếu có 10 account, hệ
thống chạy 5 account đầu, chờ hoàn tất, rồi chạy 5 account còn lại trong cùng
shard. Không có chọn account ngẫu nhiên: mọi account có assignment đều chạy
trước khi chuyển sang shard kế tiếp.

## Hướng dẫn vận hành cho người dùng

Phần này mô tả các thao tác thường dùng. Có ba workflow riêng; chúng không thay
đổi hoặc tự kích hoạt lẫn nhau.

```text
1. Crawl group đã duyệt       -> tạo lead
2. Tìm group nguồn theo query -> chỉ tạo group ứng viên
3. Facebook Search post       -> nguồn mở rộng, triển khai sau
```

### Chuẩn bị lần đầu

1. Đăng nhập thủ công một lần cho mỗi UID bằng `python -m scripts.login_facebook`.
   Mỗi UID phải có profile riêng tại `.secrets/facebook-profiles/<uid>`.
2. Cấu hình `POSTGRES_DSN`, Google Sheets và các biến multi-account trong `.env`.
3. Khai báo account và các group đã được duyệt trong `config/account_pools.yaml`.
4. Đồng bộ cấu hình và schema trước lần chạy đầu, hoặc sau mỗi lần nâng cấp schema:

```powershell
python -m scripts.init_postgres
```

### Menu tương tác

Mở menu cho người vận hành:

```powershell
python -m app.main --interactive
```

Menu hiện hỗ trợ:

```text
1. Crawl group — một account tìm group, tự gán các account có quyền xem
2. Crawl post — từ group đã duyệt, tìm bài theo keyword
3. Tìm post Facebook theo keyword
0. Thoát
```

Menu luôn yêu cầu xác nhận trước khi mở browser. Không in password, cookie,
token hoặc PostgreSQL DSN ra màn hình.

### Workflow 1 — Crawl group: tìm, xét điều kiện và gán account

Chọn mục `1` và một account discovery. Hệ thống tự xác định pool duy nhất của
account đó, tìm danh sách group theo `group_discovery.yaml`, rồi kiểm tra từng
group bằng **mọi account trong pool**. Group `PENDING` chỉ được duyệt một lần,
rồi được gán cho từng account thật sự thấy feed/post. Shard cũng tự chọn: hệ
thống ưu tiên shard còn dưới 10 group của mỗi account, hoặc tạo shard kế tiếp
khi các shard hiện có đã đầy. Kết quả nêu số group duyệt, assignment đã thêm,
không truy cập được và lỗi; audit log nằm ở `group_candidate_events`.

### Workflow 2 — Crawl post từ group đã duyệt

Chỉ các group đã có trong `config/account_pools.yaml` mới được crawl. Một group
được gán đúng account có quyền xem; account khác không tự dùng profile đó.

Chạy từ menu, hoặc dùng lệnh cho vận hành tự động:

```powershell
python -m app.main --orchestrate --pool pilot_hcm --debug
```

Menu không hỏi pool: nếu có một pool, nó tự chạy pool đó; nếu có nhiều pool,
hệ thống chạy từng pool tuần tự để tránh hai workflow ghi Google Sheets cùng lúc.

Để test nhanh mà không quét hết group, menu mục `2` mặc định chọn **Test
nhanh**: chỉ chạy shard đầu tiên và tối đa 5 group tổng cộng, phân đều luân
phiên giữa các account (với 2 account thường là 3 group + 2 group). Lệnh tương
đương:

```powershell
python -m app.main --orchestrate --pool pilot_hcm --shard 1 --max-sources-total 5 --debug
```

Chỉ dùng chế độ này để kiểm tra profile, collector, PostgreSQL và Google
Sheets; chọn **Quét toàn bộ** trong menu hoặc bỏ hai tham số trên khi vận hành
thực tế.

Chế độ menu `3=Chạy liên tục` thực hiện đầy đủ shard 1 đến shard cuối, flush
Google Sheets sau từng shard, nghỉ 30–60 giây sau shard cuối rồi quay lại shard
1. Dừng bằng `Ctrl+C`. Lệnh tương đương cho vận hành tự động:

```powershell
python -m app.main --orchestrate --pool pilot_hcm --continuous --debug
```

Kết quả đi qua: bài gốc có URL → lọc keyword → phân loại → trích xuất →
PostgreSQL chống trùng → Sheet outbox. Comment/reply, bài thiếu URL và lead
trùng không được xuất Google Sheets.

### Cấu hình tìm group nguồn theo keyword

File `config/group_discovery.yaml` là cấu hình discovery, hoàn toàn tách khỏi
`config/keywords.yaml` và `account_pools.yaml`.

```yaml
group_discovery:
  enabled: true
  queries:
    - "gia sư tphcm"
    - "phụ huynh tìm gia sư"
  max_results_per_query: 30
  account_ids: [fb_001]
```

Chạy từ menu, hoặc dùng lệnh:

```powershell
python -m app.main --discover-groups --account fb_001 --debug
```

Khi chạy bằng menu mục `1`, discovery dùng **một account** để tìm candidate,
lưu vào PostgreSQL `group_candidates`, rồi kiểm tra từng candidate bằng các
account trong cùng pool. Group đạt điều kiện truy cập sẽ được tự động duyệt,
gán cho đúng account có thể xem và đặt vào shard còn chỗ trong
`account_pools.yaml`. Candidate không truy cập được hoặc lỗi không vào lịch
crawl. Lệnh `--discover-groups` chỉ làm bước tìm candidate, không tự gán.

Discovery lưu candidate gồm URL, tên, privacy, số thành viên, tần suất post
(nếu Facebook hiển thị), query và account tìm thấy. Candidate không truy cập
được, đã duyệt hoặc gặp lỗi không được thêm vào lịch crawl. Mọi lần kiểm tra,
tự gán và lỗi đều được lưu trong PostgreSQL `group_candidate_events` để truy
vết sau này.

### Workflow 3 — Tìm post Facebook theo keyword

Workflow này hoàn toàn độc lập với group discovery và `account_pools.yaml`
assignment: account mở Facebook Search theo query, chỉ xử lý post gốc mà account
nhìn thấy, rồi dùng chung keyword filter, classifier, PostgreSQL deduplication
và Sheet outbox. Nó không thêm hoặc xóa group nguồn.

Chỉnh query tại `config/post_search.yaml`:

```yaml
facebook_post_search:
  enabled: true
  queries:
    - "cần gia sư"
    - "tìm gia sư"
  max_posts_per_query: 20
  account_ids: [fb_001]
```

Chạy từ menu mục `3`, hoặc:

```powershell
python -m app.main --search-posts --account fb_001 --debug
```

Chỉ dùng query ngắn, đã được vận hành xem xét; `keywords.yaml` vẫn là lớp lọc
lead phía sau và không tự biến mọi keyword thành truy vấn Facebook Search.

Post chứa keyword nhưng mang dấu hiệu chào bán dịch vụ như `nhận học sinh`,
`học thử`, `khóa học`, `chiêu sinh`, `bên em có gia sư` hoặc giá quảng cáo được
phân loại `TUTOR_OFFER` và bị loại. Ví dụ “Bạn đang tìm gia sư… nhận học sinh,
chỉ 600k/tháng, học thử miễn phí” không tạo lead vì người đăng đang bán dịch vụ,
không phải đang tìm người dạy.

### Quy tắc chạy tuần tự Google Sheets

Crawl group (menu `2`) và Facebook Post Search (menu `3`) cùng dùng một Sheet
và một `sheet_outbox`. Trong phiên bản hiện tại, **không chạy hai workflow này
ở hai terminal cùng lúc**: hoàn tất workflow thứ nhất rồi mới chạy workflow
thứ hai. Mỗi workflow vẫn có thể xử lý nhiều account theo batch nội bộ, giới
hạn bởi `max_concurrent_accounts`; quy tắc này chỉ cấm chạy song song hai
workflow độc lập cùng ghi Google Sheets.

Sau khi mỗi shard hoàn tất, hệ thống flush lead `PENDING` từ `sheet_outbox`
sang Google Sheets **trước** khi bắt đầu nghỉ 30–60 giây. Nếu Sheets tạm lỗi,
outbox chuyển sang `RETRY`; crawl shard tiếp theo vẫn tiếp tục và lần flush sau
sẽ thử lại.

Khi cần dừng, nhấn `Ctrl+C` và chờ thông báo dừng an toàn; không đóng cưỡng bức
terminal. Lead đã commit trước thời điểm dừng được giữ trong PostgreSQL và hệ
thống flush `sheet_outbox` trước khi thoát. Nếu máy/terminal bị tắt cưỡng bức,
lead vẫn nằm trong outbox `PENDING` và sẽ được xuất ở lần chạy hoàn tất kế tiếp.

### Khi xảy ra lỗi account

- `AVAILABLE`: có thể chạy.
- `IN_USE`: đang có worker sử dụng; không mở thêm browser cùng profile.
- `NEEDS_MANUAL_ACTION`: đăng nhập lại hoặc kiểm tra checkpoint/quyền group.
- `DISABLED`: tạm ngưng theo quyết định vận hành.

Không xóa profile để xử lý lỗi session. Đăng nhập lại đúng UID để cập nhật
session trong thư mục profile hiện có.

Nếu log báo tất cả shard là `SKIPPED`, kiểm tra trạng thái trước:

```powershell
python -m app.main --account-status
```

`IN_USE` còn sót lại sau khi terminal bị đóng hoặc dừng giữa một lượt có thể
được mở khóa **chỉ khi đã tắt tất cả terminal crawler**:

```powershell
python -m app.main --recover-in-use-accounts
```

Hoặc chọn mục `4. Check / recover account status` trong menu. Không reset
`NEEDS_MANUAL_ACTION` tự động: mở profile của UID tương ứng, xử lý login,
checkpoint hoặc quyền truy cập trước, rồi chuyển trạng thái về `AVAILABLE`.
