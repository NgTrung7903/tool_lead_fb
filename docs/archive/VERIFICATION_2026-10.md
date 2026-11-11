# Báo cáo kiểm thử

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

## Menu tương tác — 29/10/2026

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q tests/test_menu.py --basetemp=.pytest-menu`.

**9 passed in 0.58s.** Kiểm tra thoát menu không mở trình duyệt/tạo dữ liệu khách, truyền nguyên đường dẫn có khoảng trắng, chọn đúng runtime khách cho tiến trình con, Ctrl+C chờ tiến trình con dừng và chặn gửi lại bài posted/unknown/submitting. Chỉ gọi gửi khi đã chọn bài và xác nhận thao tác; hủy không gọi CLI. Không đăng Facebook thật hoặc tiếp tục phép thử đã bị người dùng yêu cầu dừng.

`run_tool.bat` gọi `menu.py` bằng Python trong `.venv`. Chức năng chính vẫn dùng CLI/desktop launcher hiện có; không tự nâng cấp EXE cũ.

## Facebook Property Tool 4.0 — 29/10/2026

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q --basetemp=.pytest-facebook-release`.

**125 passed, 1 warning in 64.51s.** Cảnh báo Starlette/httpx cũ không làm test thất bại. So với bản 106 test: thêm 17 trường hợp nguồn/workflow và 2 trường hợp bình luận dài/cắt ngắn.

- Nguồn JSON công khai/HTML JSON-LD, metadata thiếu/sai, đơn vị diện tích, tin sold, URL/redirect mạng riêng, giới hạn tải, lỗi nguồn không biến thành mock.
- Ảnh được chuẩn hóa JPEG và lưu hash; chọn/bỏ ảnh, mất/đổi snapshot, lưu và tải lại SQLite nguồn; demo có ảnh cục bộ, không cần mạng.
- Campaign nhận nguồn chung qua provider, bắt buộc xác nhận duyệt và preview còn hiệu lực; campaign demo bị chặn gửi thật.
- Chỉ bài posted có bằng chứng/permalink được chuyển sang lấy bình luận; unknown/chờ duyệt/chưa gửi bị chặn.
- Lead giữ căn/chiến dịch/tác vụ/nhóm/URL nguồn/URL bình luận đến Excel, phân loại đúng ba mức trên fixture.
- Chromium chạy giao diện chính → API thật → SQLite nguồn/campaign → poster fixture → collector fixture → mở trang kết quả theo run ID → tải và đọc XLSX → tải lại lịch sử chiến dịch. Tên chứa HTML không thực thi script.
- Collector mở nội dung dài trước khi áp giới hạn; bình luận còn dấu hiệu bị cắt được cảnh báo/chuyển xem xét khi cần.
- Toàn bộ kiểm thử cũ vẫn đạt. Ảnh QA: `.test-runs/facebook-workflow.png` và `.test-runs/lead-dashboard.png`.

Các nguồn/tài khoản/bài trong test đều là dữ liệu mô phỏng offline. Chưa nghiệm thu website bên ngoài hoặc Facebook thật. Xem [phạm vi hỗ trợ](../FACEBOOK_WORKFLOW.md) và [UAT](../UAT.md).

**EXE 4.0 đã kiểm tra trực tiếp:** `dist/FacebookLeadFilter.exe`, 271.216.136 bytes. Self-test và mọi kiểm tra HTTP trong `packaging/verify_exe.py` đều đạt: dashboard/workflow JS, nguồn demo, preview/ảnh JPEG, tạo chiến dịch mẫu, chặn gửi demo, registry, lọc lead và hai báo cáo Excel. Runtime mới được cô lập, dùng browser trong gói, không dùng tài khoản/API thật. Server thử đã đóng cùng tiến trình con. Kết quả: `dist/EXE_VERIFICATION.json`; log `.test-runs/exe-verification-d773d238a8cf4701a53593691ffbf624`. Audit manifest không có config/profile/lịch sử khách; SHA256 ở `dist/FacebookLeadFilter.sha256`.

## Facebook Lead Filter — 29/10/2026

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q --basetemp=.pytest-lead-final`

**106 passed, 1 warning in 53.97s.** Cảnh báo Starlette/httpx cũ không làm test thất bại. Có 17 trường hợp bổ sung cho luồng lead:

- Kiểm tra/chuẩn hóa link Facebook, từ chối domain ngoài, cổng lạ và link không phải bài viết.
- Liệt kê đủ 5 registry và số nhóm/từ khóa; phân loại ba trạng thái, trích điện thoại và giữ link bình luận.
- Tác vụ nền, khóa profile, dừng, lưu/khôi phục lịch sử, giữ snapshot khi lỗi.
- Sửa lỗi đọc/ghi JSON đồng thời trên Windows bằng khóa storage; phục hồi phải đọc lại sau khi lấy khóa để không ghi đè kết quả vừa hoàn tất.
- Chromium thực thi collector trên DOM Facebook mô phỏng: loại bài gốc, bình luận bài gợi ý, phần ẩn; đọc phản hồi và chống trùng mã bình luận qua nhiều snapshot; phiên không hợp lệ trả cần thao tác.
- Chromium chạy dashboard → API → worker fixture → file JSON → tải lại lịch sử → tải XLSX, kiểm nội dung bằng openpyxl; tên chứa HTML được hiển thị dạng text, có fallback dữ liệu mẫu offline.
- Bộ kiểm thử đăng bài trước đây vẫn đạt sau khi chuyển dashboard cũ sang `/posting`.

Ảnh QA giao diện: `.test-runs/lead-dashboard.png`. Mọi bài/tài khoản trong test là fixture offline. Chưa thử Facebook thật, chưa xác minh tỷ lệ lấy bình luận thực tế hoặc hiệu quả phân loại trên tập dữ liệu khách. Xem [UAT.md](../UAT.md).

**EXE mới đã kiểm tra:** PyInstaller 6.22.3 tạo `dist/FacebookLeadFilter.exe`, 271.178.068 bytes. Chạy chính EXE trong runtime kiểm thử riêng, PATH chỉ có hệ thống và cache browser ngoài gói không tồn tại: toàn bộ self-test và smoke HTTP đạt. Xác nhận assets lead, Chromium đi kèm, 5 registry, API lọc dữ liệu mẫu, Excel và API cũ. Kết quả ở `dist/EXE_VERIFICATION.json`; log `.test-runs/exe-verification-c0a5a175b3a44acd89b0f4943a4bef80`. Audit manifest không có config, profile hay dữ liệu khách. Server thử đã đóng cùng cây tiến trình con. Đây chưa phải kiểm tra trên máy khách sạch hoặc Facebook thật.

## Các lần kiểm thử trước — công cụ đăng bài

Luồng kiểm tra: cấu hình và phiên → chọn căn/nhóm → preview → gửi chiến dịch → lưu kết quả → tải lại lịch sử. Đây là kiểm thử cục bộ; API Revoland và Facebook thật chưa được nghiệm thu.

## Kết quả tự động

### Bản EXE Windows

- Bộ test mã nguồn: **89 passed, 1 warning in 54.94s**, bao gồm 6 trường hợp cấu hình dữ liệu khách/frozen runtime mới.
- PyInstaller 6.22.3 tạo `dist/RevolandFBPoster.exe` (271.112.542 bytes), có Chromium đi kèm. Bản console Windows x64 chưa ký số.
- `packaging/verify_exe.py` đã chạy chính file EXE với runtime mới, PATH hệ thống tối thiểu, bỏ PYTHONHOME/PYTHONPATH/VIRTUAL_ENV và đặt cache browser ngoài gói vào đường dẫn không tồn tại.
- Self-test frozen đạt: HTML, JavaScript, registry, SQLite, Excel và Chromium offline. Smoke HTTP đạt: dashboard, script, cấu hình ẩn key, 3 căn mẫu, xuất Excel bình luận và lịch sử.
- Audit manifest build không có config khách, profiles, browser_data hay lịch sử/ảnh khách. Server kiểm thử đã đóng cùng tiến trình con. Kết quả máy đọc ở `dist/EXE_VERIFICATION.json`.
- Chưa thử cài trên máy khách sạch và không đăng Facebook/gọi Revoland thật. Hướng dẫn ở [BUILD_EXE.md](../BUILD_EXE.md).

### Cập nhật chức năng xuất Excel

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q --basetemp=.pytest-export-final`

**83 passed, 1 warning in 46.32s.** Cảnh báo Starlette/httpx cũ không làm test thất bại. Các trường hợp bổ sung xác nhận:

- Xuất một campaign/toàn bộ lịch sử, giữ posted/unknown/running, permalink, lỗi, retry và nguồn dữ liệu; lịch sử rỗng trả file có header.
- Nhập JSON bình luận/lead, trích liên hệ, giữ số 0 đầu và trạng thái đồng bộ theo input; lead không có bình luận gốc vẫn được xuất đúng loại.
- Dữ liệu text bắt đầu bằng dấu = không biến thành công thức; ký tự XML không hợp lệ được loại bỏ; dữ liệu nhập sai/quá giới hạn bị chặn.
- HTTP download trả XLSX hợp lệ; Chromium bấm cả ba nút xuất, tải file và đọc lại nội dung bằng openpyxl, đồng thời kiểm tra thông báo JSON lỗi.
- CLI tạo cả hai loại báo cáo, chặn ghi đè file và không phục hồi/đổi task running khi chỉ xuất báo cáo.
- Cú pháp Python/JavaScript, JSON mẫu và liên kết tài liệu đã kiểm tra. Thao tác xuất không gọi Facebook/Revoland thật.

File mẫu: [examples/comments.sample.json](../../examples/comments.sample.json). Hướng dẫn dùng trên dashboard và CLI nằm ở phần 21 trong [hướng dẫn sử dụng](REVOLAND_GUIDE_2026-10.md).

### Cập nhật sau khi sửa hai lỗi P1

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q --basetemp=.pytest-p1-complete`

**63 passed, 1 warning in 37.45s.** Có 10 trường hợp hồi quy mới cho việc đọc trạng thái sau khóa, trả khóa khi validation lỗi, avatar/ảnh còn thiếu, đủ nhiều ảnh, ảnh hỏng, upload bận, thiếu tile ảnh rõ ràng và draft cũ có ảnh. Test Chromium dùng trang giả lập; chưa nghiệm thu Facebook thật.

- Campaign chỉ được đọc/validate và ghi queued sau khi giữ cả khóa runner và khóa file; test cho yêu cầu khác hoàn tất trước thời điểm lấy khóa xác nhận không gửi lại task posted.
- Upload chỉ đếm image mới trong tile có nút gỡ ảnh; ảnh phải decode/hiển thị đủ và không còn UI bận. Không tính avatar có sẵn; ảnh từ bản nháp cũ chặn gửi.
- 26 test tập trung campaign/browser đã qua trước khi chạy toàn bộ; cú pháp các file sửa và liên kết dòng trong tài liệu function đã kiểm tra.
- Hai lỗi P1 R1/R2 trong [CODE_REVIEW.md](CODE_REVIEW_2026-10-28.md) đã sửa; các vấn đề P2 còn lại vẫn được giữ nguyên.

### Mốc kiểm thử trước bản sửa P1

Lệnh: `.venv\Scripts\python.exe -u -m pytest -q --basetemp=.pytest-release`

**53 passed, 1 warning in 17.00s.** Cảnh báo là deprecation của Starlette TestClient khi dùng httpx; không phải lỗi chức năng. Môi trường Windows, Python 3.12.14, Chromium 156; phiên bản thư viện đã ghi trong `requirements-lock.txt`.

| Ranh giới | Kết quả | Bằng chứng |
|---|---|---|
| UI dựng trang và xử lý dữ liệu | Đạt | Chromium kiểm tra preview, chặn đăng dữ liệu mẫu và hiển thị chuỗi HTML như văn bản |
| UI → API | Đạt | Dashboard thật gọi FastAPI thật qua cầu ASGI trong test, gửi nội dung đã chỉnh sửa |
| API → dữ liệu | Đạt | CampaignService thật ghi SQLite riêng; mock chỉ tại ranh giới hệ thống ngoài |
| Dữ liệu → response → UI | Đạt | Kết quả đăng hiển thị, reload trang đọc đúng chiến dịch và permalink |
| Playwright nhập nội dung/ảnh | Đạt trên fixture | Toàn bộ bài dài hơn 500 ký tự, tiếng Việt, emoji và file ảnh được gửi qua trình duyệt |
| Xác nhận kết quả | Đạt trên fixture | Nhận permalink mới; nhận chờ duyệt; checkpoint sau gửi chuyển unknown |
| Chống trùng/retry | Đạt | Hai chiến dịch tạo trước, URL nhóm thêm lại, retry bỏ qua thành công, unknown không tự retry |
| Phục hồi và khóa | Đạt | Gián đoạn sau bắt đầu gửi chuyển unknown; hai service không ghi đè lần chạy đang hoạt động |
| Dữ liệu cũ | Đạt | Import JSON một lần, giữ file gốc, không tin trạng thái thành công cũ |
| Revoland adapter | Đạt trên response giả lập | 401/403/500 không thay mẫu, schema lỗi báo rõ, mảng/envelope/phân trang/ảnh được kiểm tra |
| Phiên và cài đặt | Đạt trên fixture | Cookie + dấu hiệu UI, khóa profile, lỗi xóa phiên không báo thành công, tắt lưu mật khẩu trong Preferences |
| Các module cũ | Đạt bộ test hiện có | Khôi phục schema/import, bộ lọc 20/20 dữ liệu mẫu, pipeline lead thử nghiệm |

`node --check api/static/app.js`: đạt. `pip check`: không có dependency hỏng. Parser PowerShell kiểm tra `install.ps1` và `start.ps1`: không có lỗi cú pháp.

Khởi động thực tế với dữ liệu kiểm thử riêng: `cli.py --server --port 8010` báo `Application startup complete`. Kiểm tra HTTP: dashboard 200, có script ứng dụng, API cấu hình không lộ key, danh sách trả 3 căn mẫu dưới chế độ mock. Server kiểm thử được dừng sau khi kiểm tra.

## Giới hạn

- Không dùng API key, tài khoản, cookie hay nhóm Facebook thật trong kiểm thử. HTTP ngoài bị chặn; Chromium dùng trang được intercept.
- Chưa xác nhận endpoint `/ping`, `/listings`, quy tắc phân trang và trạng thái tin là hợp đồng thực tế của Revoland. Người dùng đã chọn giữ adapter và checklist do chưa có tài liệu API.
- Selector Facebook cần kiểm tra trên nhóm mục tiêu. Thiếu xác nhận rõ ràng sẽ trả unknown thay vì tự nhận thành công. Feed bị thu gọn hoặc thông báo khác ngôn ngữ có thể cần khách xác minh.
- Không khẳng định đã được Facebook cho phép tự động hóa. Không cam kết phiên tồn tại mãi mãi hoặc tránh checkpoint.
- Chưa chạy nghiệm thu khách, thay đổi ACL bằng `start.ps1` trên máy bàn giao hay cài mới toàn bộ trên máy sạch. Hai script đã kiểm tra cú pháp; thư viện/Chromium đã cài và chạy kiểm thử trong môi trường hiện tại.
- Chưa triển khai tính năng lọc bình luận/tạo lead vào dashboard. Các module cũ tiếp tục là thử nghiệm ngoài MVP.

Hoàn tất các mục trong [UAT.md](../UAT.md) trước khi xác nhận sẵn sàng vận hành thực tế.
