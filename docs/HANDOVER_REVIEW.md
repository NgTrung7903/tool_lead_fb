# Biên bản rà soát và bàn giao Công cụ BĐS Facebook

Ngày rà soát 11/11/2026. Phiên bản bàn giao 2026.11.11-link.18, chạy trên Windows 64-bit.

## Phạm vi

Rà soát luồng ứng dụng BĐS Facebook từ trình khởi chạy, nạp bài JSON và ảnh, duyệt tin, chọn nhóm, lưu đợt, đăng tuần tự, theo dõi kết quả, lấy bình luận, tổng hợp khách hàng và xuất Excel. Kiểm thử tự động dùng trang Facebook giả lập, dữ liệu riêng và nguồn HTTP được thay bằng fixture. Bản EXE được kiểm tra riêng bằng Chromium đi kèm, SQLite, TLS, API localhost và Excel.

Kết quả cuối đạt **418/418 ca kiểm thử**, với 0 lỗi và 0 ca bỏ qua. Bộ kiểm tra EXE v18 đạt toàn bộ kiểm tra, gồm nạp phản hồi Revoland, cột Nhóm và việc phân biệt “sổ hồng” với tín hiệu “hóng” riêng biệt. Báo cáo kiểm thử có một cảnh báo deprecation từ thư viện dùng trong TestClient.

Đã kiểm tra trực tiếp link Revoland được cung cấp bằng chính EXE v18. Tin 261111-MF93 có giá bán 12 tỷ, diện tích đất 52 m², diện tích sử dụng 300 m² và 3 ảnh đã tải, kiểm tra đọc được qua API ảnh cục bộ. LINK_EXE_VERIFICATION.json ghi bằng chứng. BAI_DANG_XEM_TRUOC.txt chứa nội dung được soạn từ tin này.

Thư mục Data_tool chứa công cụ thu thập sản phẩm độc lập. legacy chứa prototype có kiểm thử tham khảo. Hai phần này phục vụ bảo trì mã nguồn và nằm ngoài phạm vi vận hành của EXE BĐS bàn giao.

## Các điểm đã xử lý

- Ô nhập link được đưa lên đầu bước 2. Công cụ đọc JSON nhúng trong trang chi tiết Revoland, đối chiếu ID bài với link và lấy imageUrls của đúng bất động sản.
- Hỗ trợ phản hồi JSON dạng data chứa một bất động sản. Giá thuê/bán, diện tích đất/sử dụng và số phòng được dựng thành nội dung theo mẫu cùng mô tả nguồn. Mẫu JSON người dùng gửi và link thử thuộc hai tin khác nhau, nên nội dung được kiểm tra theo đúng ID của link.
- Dữ liệu nội bộ như privateNote và metadata công ty được tách khỏi các trường dùng soạn bài. Link ảnh từ website được kiểm tra là HTTP(S).
- Bộ lọc trước đây coi từ “hồng” trong “sổ hồng” là “hóng” sau khi bỏ dấu, cộng thêm 10 điểm quan tâm. Đã loại phần trùng trong cụm pháp lý và thêm kiểm tra giữ tín hiệu “hóng” độc lập ở phần khác của câu.
- Bảng Khách hàng có cột Nhóm đặt cạnh bình luận, chia riêng từng nhóm trong một dòng của khách. Đã kiểm tra xem đầy đủ/thu gọn, lọc và xuất Excel.
- Test đăng nhiều nhóm đã được sửa để tạo phiên trình duyệt riêng theo từng lượt đăng tuần tự. Test xem đầy đủ bình luận dùng nội dung dài để kiểm tra đúng trường hợp tràn khung.
- Trình khởi chạy và hướng dẫn build đã được cập nhật sang bản v18. PDF hướng dẫn có trang nhập link và bài xem trước của link đã thử.
- Script dọn project nhận diện các bản v10 đến v17, cache build/test và cache Python. Có kiểm tra đường dẫn, từ chối junction/symlink và dừng khi thư mục release cũ có file lạ.

## Ma trận luồng đã rà soát

| Luồng | Nội dung đã kiểm tra | Bằng chứng |
| --- | --- | --- |
| Mở công cụ | Chọn thư mục dữ liệu theo khách, chọn cổng trống, mở lại đúng phiên bản, khóa chạy trùng một bộ dữ liệu | test_desktop_launcher, EXE_VERIFICATION |
| Nạp link Revoland | JSON chia thành nhiều đoạn, đúng ID tin, giá bán/thuê, trường thiếu, link ảnh, bài bị gỡ và phản hồi khác ID | test_revoland_source, LINK_EXE_VERIFICATION |
| Đăng nhập/phiên | Nhận biết cookie cùng trạng thái trang, checkpoint, khóa profile, báo lỗi đăng xuất | test_session, test_browser |
| Nạp JSON | Cấu trúc/alias, nạp nhanh, nhiều bài, ảnh URL/base64/file, nạp lại, lỗi ảnh và đợt nhập bị ngắt | test_json_posts, test_saved_sources, test_download_errors |
| Duyệt tin | Nội dung/ảnh snapshot, sửa nội dung, bỏ chọn ảnh, tự làm sạch HTML, trỏ vào ô lỗi | test_workflow, test_post_content_cleaning, test_error_locations |
| Chọn nhóm/lưu | Thêm nhóm, giới hạn 100 nhóm, xác nhận đã duyệt, lưu khoảng nghỉ riêng từng đợt | test_groups, test_campaign, test_workflow |
| Đăng và khôi phục | Đăng tuần tự, lưu permalink, chờ duyệt/unknown, checkpoint, retry chủ động, khôi phục sau gián đoạn | test_browser, test_campaign, test_workflow |
| Lấy bình luận | Đúng bài mục tiêu, mở nội dung dài, tối đa 5 phút mỗi bài, dừng, kết quả một phần và cập nhật lại | test_leads, test_comment_refresh |
| Tổng hợp khách | Một hồ sơ một dòng xuyên bài/nhóm, người ẩn danh/tên trùng, nhóm cạnh bình luận, bộ lọc và tìm kiếm | test_customer_rows, test_customer_hub |
| Excel | Lọc toàn bộ trang, dữ liệu khách gom theo hồ sơ, giữ nguồn/nhóm/bài/đợt và nội dung gốc | test_exports, test_customer_hub, test_workflow, EXE_VERIFICATION |
| Dọn project | Preview và xóa file sinh tự động, giữ dữ liệu khách/EXE mới, chặn file lạ và junction | test_cleanup |

## Bằng chứng trong bộ bàn giao

KIEM_THU_TU_DONG.json ghi tổng số ca kiểm thử và kết quả cuối. EXE_VERIFICATION.json ghi kết quả kiểm tra chính file EXE. RELEASE.json ghi phiên bản, kích thước và SHA256. SHA256SUMS.txt cho phép đối chiếu các file trong bộ bàn giao.

Bộ phân phối gồm một EXE, PDF có hình, hướng dẫn nhanh, JSON mẫu và các báo cáo. Các đầu vào mẫu cần thay bằng nội dung được duyệt trước khi vận hành.

Sau khi xác minh bản mới, bản v17 và ZIP bàn giao v17 được thay bằng bản v18. Thư mục dist dùng một EXE tại revoland-link-v18. CLEANUP_SUMMARY.json ghi kết quả dọn cache và bản phát hành cũ.

## Điều kiện cần nghiệm thu trên máy nhận

Các thao tác Facebook thật cần có tài khoản và nhóm mục tiêu của công ty. Người nhận điền ngày, người kiểm tra và link/ảnh bằng chứng trong NGHIEM_THU_THUC_TE.md.

- Mở EXE trên máy Windows nhận bàn giao, đăng nhập và OTP/checkpoint nếu có.
- Nạp JSON thật, đối chiếu giá, địa chỉ, thông tin liên hệ và ảnh, rồi chọn một nhóm được phép thử.
- Đăng một bài được duyệt, mở permalink và đối chiếu toàn bộ nội dung/ảnh.
- Thử nhóm có duyệt, nhóm thiếu quyền hoặc trường hợp mất kết nối theo điều kiện thử được thống nhất.
- Lấy bình luận của bài thử, dừng giữa chừng, lấy bổ sung và đối chiếu nội dung gốc.
- Kiểm tra một hồ sơ ở nhiều nhóm vẫn là một khách, cột Nhóm và Excel khớp bài gốc.
- Đóng/mở lại công cụ, kiểm tra dữ liệu, phiên và cách tiếp tục đợt.
- Nếu dùng Revoland tại /posting, đối chiếu riêng API thật, khóa truy cập và quyền dữ liệu.

Trong cùng một đợt, chạy tiếp bỏ qua nhóm đã thành công. Một đợt mới hoặc lệnh đăng lại chủ động có thể gửi lại bài. Người dùng cần kiểm tra bài chờ duyệt/chưa rõ kết quả trước khi xác nhận gửi tiếp.

## Vận hành và dữ liệu

Dữ liệu launcher mặc định ở %LOCALAPPDATA%/RevolandFBPoster/default. Tham số --customer chọn bộ dữ liệu khác. REVOLAND_DATA_DIR được ưu tiên khi đã đặt. Sao lưu toàn bộ thư mục dữ liệu của đúng khách sau khi tắt công cụ.

Các thư mục data, profiles, browser_data và cấu hình local trong workspace thuộc dữ liệu vận hành trên máy phát triển. Gói ZIP bàn giao được tạo từ danh sách file phân phối cụ thể. Kiểm tra danh mục tài nguyên nhúng của EXE xác nhận dữ liệu khách, cấu hình khách và profile đăng nhập không nằm trong gói.
