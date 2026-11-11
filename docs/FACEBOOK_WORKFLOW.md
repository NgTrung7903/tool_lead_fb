# Luồng sử dụng Công cụ BĐS Facebook

Bản bàn giao 2026.11.11-link.18. Hướng dẫn thao tác theo tên nút trong [USER_GUIDE.md](USER_GUIDE.md). Kết quả rà soát nằm trong [HANDOVER_REVIEW.md](HANDOVER_REVIEW.md).

## Mở công cụ

Mở `dist/revoland-link-v18/CongCuBDS_JSON.exe`. Trong thư mục mã nguồn, `run_tool.bat` ưu tiên môi trường Python đã cài, sau đó dùng EXE v18 nếu có.

Công cụ tự mở trình duyệt và chọn cổng trống bắt đầu từ 8000. Dữ liệu của launcher mặc định nằm ở `%LOCALAPPDATA%/RevolandFBPoster/default`. Tham số `--customer khach01` chọn bộ dữ liệu riêng. Biến `REVOLAND_DATA_DIR` được ưu tiên khi đã đặt. Mỗi bộ dữ liệu chỉ chạy một dashboard.

## Bước 1. Kết nối Facebook

Bấm **Đăng nhập Facebook** và nhập mật khẩu, OTP hoặc hoàn tất xác minh trong cửa sổ Facebook. Kiểm tra trạng thái trước khi đăng. Khi cần, dùng menu **⋯** để kiểm tra lại kết nối hoặc đăng xuất.

## Bước 2. Nạp bài đăng

Dán link chi tiết Revoland rồi bấm **Lấy tin & soạn nội dung**. Công cụ đọc JSON nhúng trong trang và đối chiếu mã tin với link. Nội dung được tạo từ các trường công khai về giá bán/thuê, vị trí, diện tích, số phòng và mô tả nguồn. Ảnh trong imageUrls được tải vào kho ảnh cục bộ để duyệt.

Link JSON/API có thể trả một bất động sản trong data hoặc mảng tin theo cấu trúc đã hỗ trợ. Mã tin khác link chi tiết được báo lỗi để người dùng kiểm tra.

Chọn file JSON rồi bấm **Nạp JSON & xem bài**. Mặc định **Nạp nhanh** tải nội dung trước, tải ảnh khi mở từng tin. Tắt tùy chọn này nếu muốn tải sẵn toàn bộ ảnh.

Chọn tin trong kho, tìm theo tiêu đề hoặc chuyển trang. Mỗi trang tối đa 100 tin. Nút xóa kho áp dụng cho bài nguồn trên máy. Các đợt đăng đã lưu dùng nội dung và ảnh riêng.

Trong **Nguồn khác**, có thể tự soạn tin, chọn ảnh từ máy, nạp kho QuinLand hoặc lấy website có JSON/JSON-LD tương thích. Website không được nhận diện sẽ báo lỗi. Thông tin giá, vị trí hoặc diện tích thiếu cần người dùng kiểm tra.

Xem cấu trúc và cách xử lý ảnh trong [JSON_POSTS.md](JSON_POSTS.md).

## Bước 3. Duyệt bài và chọn nhóm

Đọc lại nội dung, chỉnh sửa trực tiếp, kiểm tra ảnh và bỏ chọn ảnh không dùng. Thêm nhóm từng nhóm hoặc dán danh sách, sau đó kiểm tra các nhóm đã tích.

Chọn tối đa 100 nhóm cho một đợt, tùy giới hạn cài đặt. Nhập khoảng nghỉ tối thiểu/tối đa theo giây. Tích xác nhận đã duyệt rồi bấm **Lưu & chuẩn bị đăng**. Đợt lưu giữ nội dung, ảnh, nhóm và khoảng nghỉ tại thời điểm đó. Sau khi chỉnh sửa thêm, hãy lưu đợt mới.

## Bước 4. Đăng và theo dõi

Chọn đúng đợt rồi bấm **Bắt đầu đăng** và xác nhận. Công cụ xử lý lần lượt các nhóm. Giữ máy và cửa sổ chạy công cụ mở trong lúc đăng.

- **Đã xác nhận đăng** cho phép mở link bài và chuyển sang lấy bình luận.
- **Chờ admin nhóm duyệt** hoặc **Chưa rõ kết quả** cần kiểm tra bài trên Facebook. Có thể dùng **Tự kiểm tra trên Facebook** hoặc xác nhận thủ công sau khi đã đối chiếu bài thật.
- Khi Facebook yêu cầu đăng nhập/xác minh, hàng chờ dừng để người dùng xử lý.
- Kiểm tra kết quả trước khi đăng lại nhóm lỗi hoặc chưa rõ kết quả.

Dùng **Tải kết quả (Excel)** để lấy báo cáo theo nhóm.

## Lấy bình luận trong tab Khách hàng

Chọn đợt và một bài/nhóm hoặc tất cả bài đã xác nhận đăng. Chọn từ 1 đến 500 bình luận mỗi bài rồi bấm **Lấy & lọc comment**. Mỗi bài xử lý tối đa 5 phút. Có thể dừng và giữ dữ liệu đã lấy. Lấy lại bổ sung và cập nhật dữ liệu đã lưu.

Kết quả gom theo hồ sơ Facebook, mỗi khách một dòng. Cột **Nhóm** nằm cạnh các bình luận tương ứng, mỗi nhóm có một phần riêng trong dòng của khách. Dùng **Xem đầy đủ bình luận** để mở nội dung dài. Tên hiển thị giống nhau chưa đủ để gộp khách xuyên nhóm.

Lọc theo đợt, nhóm, phân loại, mức quan tâm hoặc từ khóa rồi bấm **Tải Excel theo bộ lọc**. File gồm mọi kết quả khớp bộ lọc, kể cả các trang khác. Giữ link bài và bình luận để đối chiếu. Phân loại là gợi ý, cần đọc nội dung trước khi liên hệ.

Trong **Công cụ bổ sung**, có thể lấy bình luận từ link Facebook ngoài công cụ hoặc nhập bình luận thủ công/JSON. Kết quả nhập thủ công cần tải Excel để lưu.

## Dữ liệu và nghiệm thu

Đăng bài, lấy bình luận và đăng xuất dùng phiên Facebook trên máy. Đợi tác vụ kết thúc hoặc dừng lấy bình luận trước khi đóng công cụ. Sao lưu thư mục dữ liệu của đúng khách khi chuyển máy, sau khi ứng dụng đã tắt.

Luồng Revoland cũ tại `/posting` cần API và quyền truy cập phù hợp. Nghiệm thu tài khoản, nhóm mục tiêu, checkpoint và kết quả đăng Facebook thật theo [UAT.md](UAT.md).


