# Checklist nghiệm thu trên tài khoản và API thật

Áp dụng cho bản bàn giao 2026.11.11-link.18. Kết quả kiểm thử offline nằm trong [HANDOVER_REVIEW.md](HANDOVER_REVIEW.md). Người nghiệm thu cần điền kết quả trên máy nhận, tài khoản và nhóm mục tiêu.

## Luồng website → Facebook → lead — chưa nghiệm thu hệ thống thật

- [ ] URL nguồn mục tiêu được nhận diện, trường/ảnh đúng dữ liệu thật, nguồn không hỗ trợ báo rõ.
- [ ] Website/API nguồn không có giá, diện tích hoặc pháp lý: không thêm thông tin giả.
- [ ] Bỏ chọn ảnh, nhập lại nguồn sau khi tạo chiến dịch: bài gửi vẫn khớp ảnh/nội dung đã duyệt.
- [ ] Nhóm nhận được bài, permalink và trạng thái đúng; giữ bằng chứng thực tế.
- [ ] Bài chờ duyệt/unknown không được tự lấy nhầm bình luận từ nhóm; xác minh đúng permalink trước.
- [ ] Từ bài đã đăng, lấy bình luận đúng bài và giữ mã căn/chiến dịch/nhóm sang Excel.
- [ ] Bình luận dài có phần phủ định cuối câu được mở đủ hoặc cảnh báo cần xem xét.
- [ ] Restart, tải lại lịch sử và thử lại nhóm lỗi không làm đăng trùng nhóm đã thành công.

## Luồng lọc lead mới — chưa nghiệm thu Facebook thật

- [ ] Mở EXE, đăng nhập/OTP và sử dụng lại phiên ở lần mở sau.
- [ ] Bài nhóm và bài trang mục tiêu: so nội dung/tên/mã bình luận với Facebook, không lấy nhầm bài gợi ý hoặc nội dung bài gốc.
- [ ] Bình luận dài: mở nội dung đầy đủ; phân loại không dựa trên phần bị cắt ngắn.
- [ ] Mở thêm bình luận/phản hồi, thử cách xếp hạng khác nhau; ghi số nhận diện được, không cam kết lấy đủ.
- [ ] Bài không có bình luận, bài bị xóa, nhóm riêng tư không có quyền: báo chưa nhận diện/cần thao tác.
- [ ] Phiên hết hạn, checkpoint, mất mạng, khách đóng cửa sổ: không báo đã lấy đủ, giữ snapshot đã có.
- [ ] Bấm Dừng lấy, tải lại trang và mở lại tool: dừng được, xem lại lịch sử và xuất Excel được.
- [ ] So tên, liên hệ, nguyên văn, lý do và điểm trong bảng/XLSX; review thủ công lead tiềm năng.
- [ ] Kiểm tra quyền sử dụng dữ liệu và điều kiện Meta áp dụng trước khi vận hành thực tế.

## Luồng đăng bài cũ — `/posting`

Chỉ đánh dấu đạt khi có bằng chứng thực tế. Hiện các mục dưới đây **chưa nghiệm thu**. Không ghi mật khẩu, OTP, API key hay cookie vào báo cáo.

| Kịch bản | Kết quả phải có | Bằng chứng cần ghi |
|---|---|---|
| API thật và quyền khách | Ping, danh sách, phân trang, trường dữ liệu đúng tài liệu; không lẫn căn khách khác | Response đã che thông tin nhạy cảm và hợp đồng API |
| API sai key/mất mạng/schema lỗi | Báo lỗi rõ, không hiện căn mẫu dưới nhãn dữ liệu thật | Ảnh giao diện lỗi |
| Login và OTP | Khách nhập trực tiếp trên Facebook, hoàn tất xác minh mới báo sẵn sàng | Trạng thái dashboard |
| Tái sử dụng phiên | Đóng app, mở lại, đăng thử mà không yêu cầu login khi phiên còn hiệu lực | Nhật ký hai lần mở |
| Phiên hết hạn/checkpoint | Dừng trước gửi và báo cần khách; không tiếp tục các nhóm sau | Trạng thái từng nhóm |
| Nội dung dài/tiếng Việt/emoji | Đầy đủ, khớp bản xem trước, có thông tin cuối bài | Permalink và nội dung đối chiếu |
| Nhiều ảnh, ảnh lỗi | Đúng ảnh đã chọn và thứ tự; ảnh tải lỗi được thông báo để người dùng duyệt trước khi gửi | Ảnh preview và bài thật |
| Nhóm đăng trực tiếp | Chỉ báo posted khi có permalink mới và nội dung khớp | Permalink thực tế |
| Nhóm có duyệt | Chờ duyệt được xác nhận, không coi là posted | Ảnh trạng thái trên Facebook |
| Nhóm không có quyền đăng | Không gửi, lỗi/cần thao tác rõ ràng | Kết quả nhóm |
| Mất mạng ngay sau bấm gửi | Unknown; không tự gửi lại, có bước xác minh | Task và bài/chờ duyệt trên nhóm |
| App bị đóng trước/sau gửi | Khôi phục trạng thái phù hợp, không tự lặp gửi | Lịch sử sau khởi động |
| Chạy tiếp và đăng lại | Chạy tiếp cùng đợt bỏ qua nhóm đã thành công. Tạo đợt mới hoặc chủ động retry có thể gửi lại, cần đối chiếu bài trước khi xác nhận | Lịch sử, thao tác xác nhận và bài thật |
| Retry | Chỉ xử lý nhóm lỗi, giữ nhóm thành công/chờ duyệt | Số lần retry và bài thật |
| Logout | Đóng mọi tác vụ, xóa dữ liệu; lần mở sau cần login | Thư mục phiên và status |
| Hai khách | Hai tên khách, hai thư mục/cổng; không chia sẻ phiên/key/lịch sử | Đường dẫn đã che thông tin cá nhân |
| Điều khoản và quyền sử dụng | Xác nhận mô hình được phép áp dụng, quyền nhóm và nội dung thuộc khách | Biên bản ngày 1 và nguồn chính thức hiện hành |

Biên bản: ngày, phiên bản mã, người kiểm thử, khách thử, ID căn/nhóm, kết quả, permalink hoặc ảnh minh chứng, lỗi còn lại. Chỉ bàn giao dùng thật sau khi các mục P0 đạt trên nhóm mục tiêu.

