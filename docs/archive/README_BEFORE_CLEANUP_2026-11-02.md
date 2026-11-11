# Công Cụ BĐS Facebook (Đăng Tin Nhóm & Lọc Khách Hàng)

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

## Viết lại nội dung TXT bằng AI

1. Chạy `run_tool.bat`, mở **Cài đặt → Viết lại bằng AI**, nhập OpenAI API key và bấm **Lưu cài đặt**. Model mặc định là `gpt-4.1-mini`; có thể đổi sang model hỗ trợ Chat Completions và Structured Outputs mà tài khoản được phép dùng. Biến môi trường `OPENAI_API_KEY` được ưu tiên hơn key lưu trong cấu hình.
2. Ở bước 2, chọn riêng file **TXT UTF-8** rồi bấm **Đọc TXT & xem trước**, hoặc nhập folder TXT + ảnh như trước. Nhập TXT hỗ trợ 50.000 ký tự; viết lại hỗ trợ tối đa 12.000 ký tự mỗi bài.
3. Ở bước 3, chọn giọng văn và bấm **Viết lại nội dung**. Xem bản gốc, bản viết lại, phần câu chữ thay đổi và danh sách dữ kiện.
4. Bấm **Áp dụng bản này** khi đã đọc lại; **Khôi phục bản gốc** để quay về nội dung trước lần viết lại đầu tiên. Thay đổi nội dung sẽ bỏ dấu đã duyệt. Đọc lại và đánh dấu duyệt trước khi tạo đợt đăng.

Tool trích xuất dữ kiện, viết lại, kiểm tra số/đơn vị/liên hệ/URL bằng quy tắc và đối chiếu ngữ nghĩa bằng AI. Nếu phát hiện sai lệch, tool tạo lại tối đa một lần; kết quả còn lỗi sẽ bị khóa nút áp dụng. Kiểm tra tự động có thể bỏ sót lỗi, đặc biệt quan hệ giữa số liệu và thuộc tính, nên vẫn cần người dùng đọc lại. Kiểm tra số liệu là bảo thủ: đổi cách ghi đơn vị hoặc lặp số cũng có thể bị chặn.

File TXT đầu vào không bị ghi đè. Mỗi kết quả kiểm tra được lưu riêng tại `data/paraphrases/` trong thư mục dữ liệu khách, gồm bản gốc, bản viết lại và kết quả kiểm tra; nội dung cuối cùng được chọn được lưu cùng chiến dịch khi bấm **Lưu & chuẩn bị đăng**. Key lưu trong file cấu hình cục bộ, không trả lại giao diện. Nội dung được gửi đến OpenAI khi bấm viết lại và API tính phí trên tài khoản của bạn; không có key hoặc API lỗi thì nội dung hiện tại vẫn được giữ nguyên. Chưa thay thế file EXE đóng gói cũ; dùng `run_tool.bat` trong project để chạy mã mới.

Tích hợp dùng [Structured Outputs của OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).

## Dành cho người dùng (không cần biết lập trình)

- **Chạy ngay không cần cài đặt (bản đóng gói sẵn):** mở thư mục `dist`, nhấp đúp **`FacebookLeadFilter.exe`** (kèm hướng dẫn nhanh trong `dist/HUONG_DAN_CHAY_EXE.txt`).
- **Hoặc mở từ thư mục project:** nhấp đúp **`run_tool.bat`** — trình duyệt sẽ tự động mở thẳng giao diện công cụ.
  - Nếu cổng `8000` đang bận, công cụ tự chọn cổng trống tiếp theo.
  - Nếu lỡ đóng tab trình duyệt khi công cụ vẫn đang chạy, nhấp đúp lại file để mở lại đúng tab.
- **Dành cho kỹ thuật / phát triển:** chạy **`menu_dev.bat`** (hoặc `.\run_tool.bat --dev`) để mở menu dòng lệnh kiểm thử, build EXE và CLI nâng cao.

**Luồng sử dụng trên giao diện chính (`/`):**
1. **Kết nối Facebook:** bấm *Đăng nhập Facebook*, tự nhập mật khẩu/OTP trên cửa sổ Facebook.
2. **Lấy tin cần đăng:** tự soạn tin & chọn ảnh từ máy tính, hoặc dán link trang tin BĐS hỗ trợ (có thể dùng *Tin mẫu* để làm quen).
3. **Duyệt bài & chọn nhóm:** chỉnh sửa nội dung, chọn ảnh đính kèm, thêm/chọn các nhóm Facebook và xác nhận.
4. **Đăng bài & lọc khách hàng:** bấm *Bắt đầu đăng* → theo dõi từng nhóm → bấm *Lấy bình luận & lọc lead* trên bài đã đăng hoặc chuyển sang tab **Lọc khách hàng** (`/leads`) → xuất **Excel**.

**Bắt đầu chi tiết:** [Hướng dẫn chạy project từ đầu đến cuối](../USER_GUIDE.md) — EXE, VS Code, cài đặt, demo, chạy thật, lọc lead, Excel và xử lý lỗi.

**Phạm vi hiện tại: Facebook.** Dashboard `/` đã nối luồng **lấy tin website → duyệt nội dung/ảnh → đăng nhóm → lấy bình luận từ bài đã xác nhận → lọc lead → Excel**. Xem [hướng dẫn Facebook đầy đủ](../FACEBOOK_WORKFLOW.md). Bộ lọc độc lập ở `/leads`, nguồn Revoland cũ ở `/posting`.

Hỗ trợ nguồn công khai JSON theo mẫu hoặc HTML có JSON-LD BĐS và nguồn demo tích hợp. Website cần đăng nhập/JavaScript/mapping riêng cần adapter bổ sung. Threads và Zalo chưa triển khai và được để sau. EXE giữ tên `dist/FacebookLeadFilter.exe`, giao diện có tiêu đề Facebook Property Tool.

**Định hướng đa kênh về sau:** [đặc tả mở rộng](MULTICHANNEL_REQUIREMENTS_2026-10.md). Các phần dưới là lịch sử hướng dẫn của bản lọc lead/đăng bài trước; ưu tiên hướng dẫn Facebook đầy đủ ở trên.

**Luồng chính hiện tại:** đăng nhập Facebook → nhập URL bài viết → tự lấy bình luận nhận diện được → lọc lead theo 5 bảng registry → xem lý do và xuất Excel. Không cần API Revoland. Xem [hướng dẫn lọc lead](../LEAD_FILTER.md) và [danh sách registry](../REGISTRIES.md).

Mở `dist/FacebookLeadFilter.exe` hoặc chạy `.\start.ps1 -Customer khach01` trong VS Code. Giao diện chính ở `/`; công cụ đăng bài cũ ở `/posting`. Chưa nghiệm thu việc lấy bình luận trên Facebook thật; kết quả được ghi rõ là một phần, không cam kết lấy đủ.

**Các phần dưới đây mô tả công cụ đăng bài cũ, áp dụng khi mở `/posting`.**

**Bản Windows EXE:** xem [cách chạy và build](../BUILD_EXE.md). File mới là `dist/FacebookLeadFilter.exe`, có Chromium đi kèm; dữ liệu khách được giữ ngoài gói.

**Dành cho người sử dụng:** đọc [Hướng dẫn sử dụng chi tiết](REVOLAND_GUIDE_2026-10.md), gồm cài đặt trong VS Code, chế độ mẫu khi chưa có API, phiên Facebook, nhóm, preview, kết quả, retry và xử lý lỗi.

Ứng dụng cục bộ để chọn căn từ API Revoland, xem trước nội dung/ảnh và đăng lần lượt vào các nhóm bằng phiên trình duyệt của khách. Khách tự nhập mật khẩu/OTP trên Facebook. Phiên còn hiệu lực được tái sử dụng; Facebook vẫn có thể yêu cầu đăng nhập hoặc xác minh lại.

**Trạng thái:** đã bổ sung cơ chế bảo vệ luồng đăng và kiểm thử tự động. Chưa nghiệm thu API Revoland và nhóm Facebook thật. Không cam kết tránh checkpoint hay được Facebook cho phép chỉ vì dùng phiên của khách. Xem [checklist nghiệm thu](../UAT.md) trước khi bàn giao.

Hai lỗi P1 về trạng thái chiến dịch cũ và tính nhầm avatar là ảnh upload đã được sửa, kèm test hồi quy. Các phát hiện P2 còn lại được ghi trong [review mã nguồn](CODE_REVIEW_2026-10-28.md). Xem thêm [giải thích toàn bộ luồng](PROJECT_FLOW_2026-10.md) và [tóm tắt từng function](FUNCTION_REFERENCE_2026-10.md).

## Xuất Excel

Dashboard có **Xuất chiến dịch đang xem**, **Xuất toàn bộ lịch sử** và mục **Xuất bình luận / lead ra Excel**. Bình luận/lead được nhập từ JSON; không tự crawl Facebook hoặc tạo lead trên Revoland. Có nút tải JSON mẫu, hoặc dùng [file mẫu](../../examples/comments.sample.json).

```powershell
# Đặt đúng thư mục khách nếu dashboard chạy bằng start.ps1 -Customer khach01
$env:REVOLAND_DATA_DIR = "$env:LOCALAPPDATA\RevolandFBPoster\khach01"
.\.venv\Scripts\python.exe cli.py --export-posts
.\.venv\Scripts\python.exe cli.py --export-comments .\examples\comments.sample.json
```

CLI in đường dẫn file trong `data/exports` của khách. Có thể dùng `--campaign ID_CHIEN_DICH` cùng `--export-posts` hoặc `--output DUONG_DAN.xlsx`. File đã tồn tại sẽ không bị ghi đè. Xem phần 21 trong [hướng dẫn chi tiết](REVOLAND_GUIDE_2026-10.md).

## Cài và chạy trên Windows

Cài Python 3.12 trở lên, có Python Launcher `py`. Trong PowerShell tại thư mục project:

```powershell
.\install.ps1
.\start.ps1 -Customer khach01
```

Mở `http://127.0.0.1:8000`. Nếu PowerShell chặn script, có thể chạy từng lệnh Python bên dưới hoặc dùng chính sách chạy script được quản trị máy cho phép.

`start.ps1` lưu cấu hình, lịch sử và phiên tại `%LOCALAPPDATA%\RevolandFBPoster\khach01`, tách khỏi thư mục OneDrive/mã nguồn, giới hạn quyền thư mục cho tài khoản Windows hiện tại và SYSTEM. Mỗi khách dùng một tên khác; chạy khách thứ hai bằng một cổng khác:

```powershell
.\start.ps1 -Customer khach02 -Port 8001
```

Mô hình MVP là **mỗi tiến trình phục vụ một khách cục bộ**, không phải server nhiều tài khoản truy cập qua Internet. Chỉ bind loopback. Không đưa profile vào Git, đồng bộ đám mây hay gửi profile cho người khác. Chromium có thể dùng cơ chế bảo vệ cookie của hệ điều hành; ứng dụng không bổ sung một kho phiên mã hóa độc lập. Người có quyền tài khoản Windows vẫn có thể truy cập dữ liệu.

Cài/chạy thủ công:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m playwright install chromium
$env:REVOLAND_DATA_DIR = "$env:LOCALAPPDATA\RevolandFBPoster\khach01"
.\.venv\Scripts\python.exe cli.py --server --port 8000
```

Nếu không đặt `REVOLAND_DATA_DIR`, ứng dụng dùng cấu hình/profile trong thư mục project để tương thích bản cũ. Đóng ứng dụng và trình duyệt trước khi di chuyển dữ liệu. Không trộn profile, cấu hình hay lịch sử của hai khách. Các module crawl/bình luận cũ là thử nghiệm sau MVP, không được nối vào dashboard đăng bài.

## Luồng sử dụng

1. Mở cấu hình, nhập API URL và key, tắt dữ liệu mẫu. Bấm **Lưu & kiểm tra kết nối**. API key đã lưu không trả về giao diện; để trống để giữ key cũ.
2. Mở cửa sổ Facebook và tự đăng nhập/xác minh. Không gõ mật khẩu hoặc OTP vào dashboard. Kết quả đăng nhập được theo dõi đến khi hoàn tất/hết thời gian.
3. Thêm URL nhóm bạn có quyền đăng. Tool chuẩn hóa URL và chặn nhóm trùng. Danh sách mới không tự thêm nhóm mẫu.
4. Chọn căn, kiểm tra toàn bộ nội dung và ảnh, chọn nhóm rồi bấm đăng. Nếu dữ liệu căn thay đổi sau preview, cần xem lại.
5. Theo dõi từng nhóm. Có thể mở lại lịch sử sau khi tải lại trang hoặc khởi động lại.
6. Retry chỉ nhóm thất bại/cần thao tác. **Tiếp tục nhóm chưa gửi** xử lý phần còn lại sau khi bạn giải quyết phiên/xác minh.

Dữ liệu mẫu chỉ để xem thử giao diện; **không được gửi lên Facebook và không sinh kết quả đăng giả**. Để chạy luồng gửi tự động, cần API thật và phiên thật. Bộ kiểm thử sử dụng dữ liệu/trang giả lập riêng.

## Ý nghĩa kết quả và chống trùng

| Kết quả | Ý nghĩa |
|---|---|
| `posted` | Nhìn thấy toàn bộ nội dung đã duyệt trong bài có permalink mới và thời gian “Vừa xong/Just now”, hoặc khách xác minh bằng permalink đúng nhóm |
| `pending_approval` | Có thông báo xác nhận bài vừa gửi đang chờ duyệt, hoặc khách xác minh trực tiếp |
| `failed` | Thao tác chưa đến bước gửi, có thể thử lại |
| `action_required` | Cần đăng nhập/xác minh hoặc trình duyệt đang bận; các nhóm sau dừng lại |
| `unknown` | Đã bắt đầu gửi nhưng chưa xác nhận được, hoặc dữ liệu cũ chưa đáng tin; **không tự retry** |
| `skipped_duplicate` | Cùng căn đã đăng/đang chờ duyệt tại cùng URL nhóm |

Khi `unknown`, mở Facebook kiểm tra nhóm, chọn **Kiểm tra và xác nhận**: đã đăng (cần permalink), chờ duyệt, hoặc chắc chắn chưa gửi/bị từ chối. Chỉ xác nhận chưa gửi khi đã kiểm tra cả bài đang chờ duyệt. Khi chưa rõ kết quả, không tạo chiến dịch mới để né kiểm tra.

SQLite lưu trạng thái trước khi bấm gửi, phục hồi tác vụ bị gián đoạn và giữ lịch sử chống trùng qua lần khởi động. Khóa tiến trình ngăn chiến dịch chạy chồng; profile có khóa riêng cho login/check/post/logout. Chống trùng dùng ID căn và URL nhóm chuẩn hóa, bao gồm trường hợp xóa rồi thêm lại nhóm.

Lịch sử JSON bản cũ có thể chứa thành công giả lập nên được nhập một lần vào SQLite với nhãn `legacy`; các thành công cũ chuyển thành **cần xác minh**, không tự coi là đã đăng thật. File gốc được giữ nguyên. Sau khi xác minh lịch sử cũ, tạo chiến dịch mới từ API thật để tiếp tục.

Không thể bảo đảm chính xác một lần gửi trên một giao diện bên ngoài: mất kết nối sau click có thể khiến Facebook nhận bài dù tool không nhận xác nhận. Vì vậy trường hợp mơ hồ bắt buộc kiểm tra thủ công.

## Hợp đồng API Revoland cần xác nhận

Adapter hiện dùng:

- `GET {base_url}/ping`: 200 hoặc 204.
- `GET {base_url}/listings?page=N`: Bearer API key; trả mảng, `{ "data": [...] }` hoặc `{ "listings": [...] }`.
- Phân trang tùy chọn: `{ "data": [...], "meta": { "last_page": 3 } }`. Adapter đọc tối đa 100 trang.
- Bản ghi cần `id`, `code`, `title`, `price_text`, `location`, `description`; có thể thêm `area_m2`, `bedrooms`, `bathrooms`, `media_urls`, `legal_status`, `revoland_url`, `status`.
- API danh sách phải cung cấp đúng tập tin đã đăng thuộc khách. Căn có trạng thái khác `available`, `published`, `active` bị chặn gửi.
- Ảnh là URL HTTP(S) tải được từ máy khách. Tải và xác minh tất cả ảnh, tối đa 20 MB mỗi ảnh. Một ảnh lỗi chặn tạo chiến dịch; không âm thầm gửi thiếu ảnh.

Endpoint và schema này là **hợp đồng adapter hiện tại**, chưa phải xác nhận API thật của Revoland. Nếu API thực tế khác, cần sửa adapter và kiểm thử theo tài liệu/response được cung cấp. Live API lỗi sẽ báo lỗi, không thay bằng căn mẫu. Không tự thêm khẳng định pháp lý vào nội dung.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Test tự tạo dữ liệu trong `.test-runs/`, không dùng cấu hình, phiên hay lịch sử khách; HTTP ngoài bị chặn. Browser test dùng Chromium với trang Facebook giả lập được intercept, không đăng bài thật. Chạy phần không cần Chromium: `python -m pytest -m "not browser" -q`.

Xem [báo cáo kiểm thử](VERIFICATION_2026-10.md) và [checklist kiểm thử thực tế](../UAT.md). Các bài kiểm thử cục bộ không chứng minh selector vẫn hoạt động trên mọi giao diện Facebook.

## CLI

```powershell
.\.venv\Scripts\python.exe cli.py --login-fb
.\.venv\Scripts\python.exe cli.py --check-session
.\.venv\Scripts\python.exe cli.py --list-listings
.\.venv\Scripts\python.exe cli.py --list-groups
.\.venv\Scripts\python.exe cli.py --post --listing ID_CAN --groups ID_NHOM_1,ID_NHOM_2
.\.venv\Scripts\python.exe cli.py --retry ID_CHIEN_DICH
.\.venv\Scripts\python.exe cli.py --logout-fb
```

CLI đăng ngay nội dung định dạng từ căn; dùng dashboard nếu cần chỉnh sửa/xem trước. Đặt cùng `REVOLAND_DATA_DIR` để CLI và dashboard dùng đúng khách. Đóng server trước khi bảo trì/chuyển dữ liệu. Xóa phiên là xóa cục bộ; để thu hồi phía Facebook, dùng phần mật khẩu/bảo mật trong tài khoản Facebook.
