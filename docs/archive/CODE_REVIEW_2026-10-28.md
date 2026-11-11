# Review toàn bộ project — 28/10/2026

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

Phạm vi: Python ứng dụng và kiểm thử, JavaScript/HTML, schema, registry JSON, script PowerShell và khai báo dependency. Không review mã thư viện trong `.venv`, cache trình duyệt hoặc dữ liệu cá nhân. Đây là review chức năng/kiến trúc, không phải một đợt kiểm toán bảo mật chuyên sâu. Chưa có tài liệu API Revoland hoặc phiên/nhóm Facebook thật để nghiệm thu.

Bản review gốc ghi nhận các phát hiện bên dưới. Cập nhật sau yêu cầu sửa: **R1 và R2 đã sửa**, có test hồi quy; **R7 đã sửa khi nối xuất Excel vào UI/CLI**. R3–R6 vẫn chưa xử lý. Phần mô tả/probe trước sửa được giữ để giải thích lỗi.

## Phát hiện theo mức ưu tiên

### R1 — P1: Trạng thái cũ có thể khiến cùng chiến dịch gửi lại

**Đã sửa:** `start_campaign()` lấy cả khóa runner và khóa file rồi mới đọc/validate campaign và chuyển queued. Test `test_start_reads_latest_tasks_after_acquiring_locks` điều khiển một yêu cầu khác hoàn tất trước lúc lấy khóa và xác nhận engine chỉ được gọi một lần. Test lỗi validation xác nhận hai khóa được trả lại.

Vị trí: `services/campaign_service.py:152–162`.

`start_campaign()` đọc đối tượng campaign trước khi lấy khóa, rồi sau khi lấy khóa ghi lại đối tượng đó với trạng thái queued. Nếu request B đã đọc bản pending, request A chạy xong trước lúc B lấy được khóa, B sẽ ghi đè kết quả A bằng bản pending cũ. `_run()` đọc lại đúng bản đã bị ghi đè; `_prior()` lại bỏ qua chính campaign đang chạy nên cùng task có thể được gửi lần nữa.

Probe điều khiển thứ tự thao tác bằng đối tượng snapshot cũ, dùng engine giả lập: `STALE_SNAPSHOT_SAME_CAMPAIGN_POST_CALLS: 2`. Đây là mô phỏng thứ tự có thể xảy ra, không phải test tải chứng minh tần suất xảy ra ngoài thực tế.

Đề xuất: lấy cả khóa trong tiến trình và khóa file trước khi đọc/kiểm tra campaign; sau đó đọc bản mới nhất từ SQLite để chuyển trạng thái. Nên có cập nhật trạng thái có điều kiện hoặc số phiên bản trong transaction. Thêm regression test cho hai request cùng campaign với validation bị trì hoãn; test hiện tại mới bảo vệ các lần chạy đang thực sự giữ khóa.

### R2 — P1: Ảnh có sẵn trong dialog bị tính nhầm thành ảnh bài đăng

**Đã sửa:** chụp danh tính các image có sẵn trước upload; chỉ đếm image mới trong tile có nút gỡ ảnh, đã decode/hiển thị, đủ đúng số lượng và không còn UI báo upload bận. Có ảnh đính kèm từ draft cũ sẽ chặn trước gửi. Chromium regression test bao phủ avatar đơn, thiếu ảnh, đủ nhiều ảnh, ảnh hỏng, đang upload và ảnh không thuộc tile rõ ràng. Nếu Facebook đổi cấu trúc tile/nút gỡ ảnh, tool sẽ báo chưa xác nhận ảnh và không bấm gửi; cần nghiệm thu selector thật.

Vị trí: `services/poster_engine.py:88–95`.

Bộ đếm upload tính mọi `img` có src chứa `scontent`, gồm cả avatar có sẵn. Với một ảnh cần gửi, avatar đã đủ làm bộ đếm đạt 1 và tool có thể bấm gửi trước khi có preview ảnh mới. Với nhiều ảnh, số ảnh xác nhận cũng có thể bị đếm dư.

Probe Chromium có avatar nhưng input file không tạo preview mới vẫn cho kết quả: `PHOTO_GATE_WITH_ZERO_NEW_PREVIEWS: posted SUBMIT_CALLS: 1`. Probe này không chứng minh Facebook thật mất ảnh, nhưng chứng minh điều kiện kiểm tra hiện tại không bảo đảm ảnh mới đã tải xong.

Đề xuất: ghi nhận attachment trước upload, chỉ đếm attachment mới trong vùng media của composer, đợi preview tải thành công và trạng thái upload kết thúc. Avatar/ảnh giao diện không được tính vào attachment.

### R3 — P2: Preview chưa khóa nội dung thực của ảnh

Vị trí: `api/server.py:190`, `api/static/app.js:81`, `services/revoland_service.py:192`.

Preview hiển thị URL ảnh bên ngoài, token chỉ băm dữ liệu JSON của căn. Đến khi tạo chiến dịch, backend mới tải bytes ảnh. Nếu cùng URL được thay nội dung giữa hai bước, token không đổi nhưng ảnh gửi khác ảnh khách vừa duyệt. Snapshot riêng từng chiến dịch đã tránh ghi đè ảnh giữa các campaign; chưa xử lý khoảng trống giữa preview và download.

Đề xuất: tải ảnh ngay khi tạo preview, lưu snapshot và hash, hiển thị ảnh snapshot qua endpoint cục bộ rồi dùng chính snapshot đó để gửi. Đây là phân tích tĩnh, chưa tái hiện với Revoland thật.

### R4 — P2: Schema có thể biến dữ liệu thiếu thành thông tin chắc chắn

Vị trí: `models/schema.py:39–47`, `services/revoland_service.py:178`.

Thiếu dữ liệu phòng ngủ/phòng tắm sẽ tự nhận 2; thiếu diện tích thành 0; thiếu status thành available. Bộ format lại in các thông số này vào bài. API thiếu trường không đồng nghĩa căn có 2 phòng hoặc đang được phép đăng.

Đề xuất: dùng giá trị nullable cho thông tin chưa biết, chỉ hiển thị trường thật sự có; chuẩn hóa trạng thái xuất bản/khả dụng bằng adapter theo hợp đồng API. Đặc biệt phải xác nhận tập căn đã đăng và quyền sở hữu ở API thật.

### R5 — P2, ngoài MVP: Gửi lại lead thất bại bị chặn là bình luận trùng

Vị trí: `services/comment_pipeline.py:46–57`.

Hash bình luận được thêm vào `_processed_hashes` trước khi gọi Revoland. Nếu đồng bộ lead thất bại, ingest cùng bình luận sẽ trả duplicate_skipped; không có hàng chờ retry lead riêng. Probe: `LEAD_FAILED_REPLAY: lead_sync_failed duplicate_skipped API_CALLS: 1`.

Đề xuất: tách trạng thái đã tiếp nhận, đã phân loại và đã đồng bộ; retry đối tượng lead đang failed bằng idempotency key. Không chỉ xóa hash rồi gửi lại mù quáng vì lần gọi có thể đã được API nhận nhưng response bị mất.

### R6 — P2, ngoài MVP: Nhánh cache báo cập nhật lead nhưng không cập nhật

Vị trí: `services/revoland_client.py:38–48`.

Khi dedup key đã có trong cache, hàm trả updated_existing và thông báo đã bổ sung ghi chú; không có request update và payload cache cũng không đổi. Probe gửi note thứ hai nhận `updated_existing` nhưng `ACTUAL_NOTE: first`.

Đề xuất: triển khai update theo hợp đồng Revoland hoặc trả existing_skipped trung thực. Cache chỉ nằm trong RAM, chưa bảo đảm chống trùng sau khởi động lại.

### R7 — P2, ngoài MVP: Excel báo đã tạo lead dù mới chỉ lọc

**Đã sửa:** exporter dùng nhãn Lead tiềm năng/Cần xem xét/Bỏ qua cho classification, chỉ ghi đã đồng bộ theo bản ghi khi có cả sync_status=synced và mã lead. JSON nhập được ghi rõ là dữ liệu người dùng cung cấp; không gọi API tạo/xác minh lead. Dashboard và CLI đã có luồng xuất file kèm test đọc lại XLSX.

Vị trí: `services/excel_exporter.py:99`, `services/browser_manager.py:178`.

Exporter gán nhãn “Đã Tự Tạo Lead” chỉ theo classification LEAD_POTENTIAL. `process_and_export_leads()` chỉ phân loại và xuất Excel, không gọi API tạo lead, nên nhãn này có thể sai cả khi không hề đồng bộ Revoland.

Đề xuất: hiển thị “Lead tiềm năng” cho classification; trạng thái tạo lead phải lấy từ kết quả đồng bộ có xác nhận. Đây là phân tích tĩnh theo đường gọi hiện có.

## Những giới hạn khác cần biết

- `RevolandService.get_listing_by_id()` tải lại toàn bộ danh sách, gồm mọi trang. Preview và create sẽ lặp chi phí gọi API; nên có endpoint detail/cache khi đã biết hợp đồng thật.
- `_prior()` đọc và parse toàn bộ lịch sử cho từng nhóm. SQLite hiện chứa JSON campaign trong một cột, chưa có bảng task/index theo căn và nhóm; lịch sử lớn sẽ chậm, UI cũng tải toàn bộ campaign.
- Chưa có giới hạn/thu gom ảnh tạm; mỗi lần tạo campaign tạo snapshot mới. Không nên xóa snapshot còn được campaign chưa hoàn tất tham chiếu.
- BrowserLeadManager dùng `browser_data/` và đường xuất trong project, không dùng `REVOLAND_DATA_DIR` hay khóa profile của MVP. Không nối module này vào dashboard nhiều khách khi chưa thống nhất lưu trữ.
- FacebookService là dịch vụ manual-assisted cũ lưu RAM. Docstring nhắc Graph API nhưng không có code gọi Graph API; access_token được lưu mà chưa dùng.
- Cơ chế xác nhận Facebook hỗ trợ một số cấu trúc và ngôn ngữ cụ thể. Bài bị thu gọn, timestamp khác hoặc dialog thay đổi có thể về unknown và cần kiểm tra. Không có test nào chứng minh selector ổn định trên nhóm thật.
- API execute/retry đổi mọi ValueError thành HTTP 404, kể cả campaign có trạng thái không hợp lệ; nên phân biệt not-found và conflict/validation.
- CLI `--post` không truyền listing/group có thể chọn căn đầu và hai nhóm đầu, không có preview chỉnh sửa; cần dùng tham số rõ ràng khi vận hành.
- Giao diện phụ thuộc Tailwind và Font Awesome CDN; test browser hiện chặn CDN nên chưa kiểm chứng hình thức thực khi CDN tải lỗi. `start.ps1` kiểm tra cú pháp, chưa xác nhận ACL đầy đủ trên một máy sạch.
- API key lưu trong file cấu hình; profile chứa phiên đăng nhập. Cách tách theo khách là theo thư mục/tiến trình trên máy, không có hệ thống đăng nhập nhiều người hay phân quyền web. Không mở cổng ra Internet dựa trên cấu hình hiện tại.

## Kiểm thử và kết luận

Bộ test chuẩn chạy lại: **53 passed, 1 warning in 50.31s**. Cảnh báo deprecation Starlette/httpx không làm test thất bại. Probe ảnh riêng: **1 passed** nghĩa là tái hiện được lỗi R2, không phải khẳng định chức năng upload đúng. R1/R5/R6 cũng được tái hiện bằng kiểm tra cô lập, không dùng dịch vụ thật.

Kết quả 53 test ở trên là mốc review trước khi sửa. R1/R2 và R7 đã được bổ sung test và sửa sau đó; xem [VERIFICATION.md](VERIFICATION_2026-10.md) cho kết quả mới. R3/R4 chưa xử lý; R5/R6 thuộc phần thử nghiệm sau MVP, cần sửa trước khi bật tự đồng bộ lead.

Luồng chính có cấu trúc đủ để tiếp tục phát triển, nhưng chưa thể khẳng định sẵn sàng vận hành thực tế. Điều kiện còn lại là sửa các lỗi trên và hoàn tất [UAT.md](../UAT.md) với API/nhóm mục tiêu.
