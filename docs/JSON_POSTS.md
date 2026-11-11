# File JSON bài đăng

Luồng chính trên giao diện là dán link Revoland hoặc link JSON/API rồi bấm **Lấy tin & soạn nội dung**. Với Revoland, công cụ đọc đúng bất động sản theo ID trong link và soạn bài từ dữ liệu công khai. JSON theo mẫu phản hồi có thể dùng dạng `{"code":200,"status":true,"data":{...}}`, với các trường `id`, `title`, `description`, `transactionType`, `location`, `propertyDetails`, `priceDetails` và `imageUrls`. Mô tả HTML được làm sạch, giữ nội dung và xuống dòng. Giá thuê được phân biệt với giá bán, diện tích đất và diện tích sử dụng được ghi riêng.

Tại bước 2, chọn file `.json` rồi bấm **Nạp JSON & xem bài**. Mặc định **Nạp nhanh** lưu nội dung và đường dẫn ảnh, chỉ tải ảnh của bài khi bạn chọn xem; ảnh đã tải được lưu để lần sau mở ngay. Tắt **Nạp nhanh** để tải sẵn toàn bộ ảnh về máy; chọn bài trong danh sách để duyệt và đăng vào nhóm. Nạp file chưa gửi bài lên Facebook.

File mẫu để thử: `bai_dang_mau.json` trong bộ bàn giao, hoặc bấm **Tải file JSON mẫu** trên giao diện. Mẫu chứa hai bài minh họa không có ảnh; thay bằng nội dung thật trước khi đăng.

## Cấu trúc dành cho bên chuẩn bị dữ liệu

```json
{
  "posts": [
    {
      "title": "Căn hộ Quận 7",
      "content": "Bán căn hộ Quận 7\nDiện tích: 72 m²\nGiá: 2,85 tỷ, chưa gồm phí.\nĐang làm sổ.",
      "images": [
        "https://website-cua-ban.vn/anh/can-ho-1.jpg",
        "https://website-cua-ban.vn/cdn-cgi/image/width=1200/anh/can-ho-2.jpg",
        "C:/Anh/can-ho-3.jpg"
      ],
      "source_url": "https://website-cua-ban.vn/tin/can-ho-1"
    }
  ]
}
```

- `content`: toàn bộ nội dung muốn đăng, bắt buộc, giữ nguyên khi nạp. Cũng nhận `post_text`, `description`, `text`, `message`, `body`, `caption`.
- `title`: tên bài trong danh sách để người dùng chọn; không tự chèn vào `content`. Nếu bỏ qua, dùng dòng đầu có chữ của nội dung.
- `images`: danh sách ảnh (cũng nhận `media_urls`, `image_urls`, `photos`, `pictures`, `image`). Mỗi ảnh có thể là:
  - link HTTP(S) công khai — kể cả link đi qua **Cloudflare**;
  - object có `url`/`src` (ví dụ `{"url": "https://..."}`);
  - ảnh base64 dạng `data:image/jpeg;base64,...`;
  - đường dẫn file trên máy (`C:/Anh/a.jpg` hoặc `file:///C:/Anh/a.jpg`).
- `source_url`: link bài nguồn, tùy chọn. Dùng làm `Referer` khi tải ảnh (vượt chống hotlink) và để ghép đường dẫn ảnh tương đối.

Nhận mảng bài trực tiếp, một bài riêng hoặc object có `posts`, `listings`, `data`, `items`, `records`.

## Không giới hạn

Không giới hạn dung lượng file, số bài mỗi file, số ảnh mỗi bài, độ dài nội dung hay dung lượng/megapixel ảnh. Ảnh rất lớn được thu nhỏ còn cạnh dài 4096 px khi lưu (Facebook vẫn tự nén ảnh). Ảnh JPG, PNG, WebP, AVIF, GIF, BMP… đều được chuyển về JPEG.

File lớn được nạp theo từng đợt 200 bài ở chế độ nhanh, hoặc 20 bài khi tải sẵn ảnh, và hiển thị tiến độ. Ảnh được tải song song (8 luồng), lưu xuống đĩa sau mỗi nhóm tối đa 32 ảnh để tránh giữ toàn bộ ảnh trong RAM. Lỗi kết nối hoặc máy chủ tạm thời được tự thử lại tối đa 2 lần. Bài trùng lặp hoàn toàn trong cùng file chỉ được giữ một bản. Nạp lại cùng dữ liệu cập nhật bản đã lưu. File JSON đầu vào không bị ghi đè.

## Ảnh qua Cloudflare

1. Tool tải ảnh với header giống trình duyệt Chrome (User-Agent, `Accept: image/*`, `Referer` = `source_url` hoặc trang gốc của ảnh). Cách này xử lý được phần lớn trường hợp Cloudflare chặn bot đơn giản hoặc chống hotlink.
2. Nếu Cloudflare vẫn chặn (trang "Just a moment…", `cf-mitigated: challenge`, HTTP 403/429/503 từ Cloudflare), tool mở một cửa sổ Chromium riêng để tải ảnh như khi bạn mở link trên trình duyệt. Nếu trang yêu cầu bấm **Xác minh bạn là con người**, hãy bấm trong cửa sổ đó (chờ tối đa khoảng 2,5 phút mỗi ảnh). Cookie xác minh được lưu trong `browser_data/image_downloader` nên các lần sau thường qua ngay.
3. Tắt bước trình duyệt (ví dụ máy chủ không có màn hình) bằng biến môi trường `REVOLAND_IMAGE_BROWSER=0`.

## Khi ảnh vẫn lỗi

Ảnh nào không tải được **không làm hỏng cả đợt nạp**: bài vẫn được lưu với các ảnh tải thành công, danh sách ảnh lỗi (kèm lý do) hiện trong thông báo sau khi nạp và ngay dưới phần ảnh khi chọn bài ở bước 3. Hãy kiểm tra lại trước khi đăng.

Nếu Google Cloud/Firebase báo tài khoản thanh toán đã đóng, cần bên cung cấp dữ liệu khôi phục kho ảnh hoặc gửi ảnh/link thay thế — không thể phục hồi ảnh từ một kho đang bị khóa.

Sau khi nạp, người dùng chọn từng bài, kiểm tra nội dung và ảnh, chọn nhóm và lưu đợt đăng. Chỉ bấm **Bắt đầu đăng** mới gửi thật lên Facebook.

Nếu bài đã hiện nhưng thiếu ảnh do lỗi kết nối, hãy nạp lại file JSON khi mạng hoạt động. Tool cập nhật bài cũ theo cùng dữ liệu, không tạo thêm bản trùng. Nếu nạp file lớn bị gián đoạn, các đợt đã hoàn tất vẫn được lưu.

## Đọc và xóa kho bài đã lưu

Danh sách chỉ đọc tối đa 100 tiêu đề mỗi trang, có tìm kiếm theo tiêu đề và nút Trang trước/Trang sau. Nội dung chi tiết chỉ đọc khi chọn bài. Các ảnh tải thành công của bài không thay đổi được dùng lại khi nạp lại cùng file.

- **Xóa bài đang chọn** xóa một bài khỏi kho trên máy.
- Mở **Chọn nhiều bài để xóa**, đánh dấu từng bài hoặc **Chọn tất cả bài trên trang này**, rồi bấm **Xóa các bài đã chọn**.
- **Xóa toàn bộ kho bài đã lưu** xóa tất cả bài, kể cả các bài không nằm trên trang đang xem hoặc không khớp từ khóa tìm kiếm.

Tool yêu cầu xác nhận trước khi xóa. Chức năng này không xóa bài trên Facebook hoặc các đợt đăng đã chuẩn bị. Các file ảnh được giữ để những đợt đăng đang tham chiếu vẫn hoạt động. Nạp lại JSON sẽ thêm lại các bài đã xóa. Không xóa bài trong lúc đang nạp file.

## Nội dung có mã HTML

Tool tự chuyển nội dung HTML từ JSON thành văn bản thường khi xem trước và soạn bài đăng: `<br>` thành xuống dòng, các đoạn và danh sách giữ bố cục, thẻ định dạng được bỏ đi, `&nbsp;`/`&amp;`/`&lt;` được giải mã. Nội dung script/style không đưa vào bài. Giá, diện tích và nội dung chữ được giữ lại.

Bộ lọc áp dụng cả bài đã lưu trước đây, không cần nạp lại file. JSON gốc và định danh bài không thay đổi. Với văn bản thường, tool giữ nguyên xuống dòng và khoảng cách.

Nếu dán thêm nội dung có mã HTML vào ô soạn bài, bấm **Làm sạch mã HTML**, đọc lại kết quả và đánh dấu đã duyệt lại. Tool chặn lưu đợt đăng khi nội dung tùy chỉnh còn cần chuyển HTML, để bạn kiểm tra đúng văn bản sẽ đăng.

## Tool tự đưa đến vị trí cần sửa

Khi thiếu nội dung, chưa chọn nhóm, chưa đánh dấu đã duyệt hoặc nhập sai một trường, tool tự mở mục đang thu gọn, cuộn đến vùng liên quan, viền đỏ và đặt con trỏ/focus vào ô đó. Hướng dẫn sửa xuất hiện ngay cạnh ô, không có nút chuyển tới lỗi. Đánh dấu lỗi được gỡ khi bạn sửa thông tin.

Lỗi dữ liệu JSON có số thứ tự bài trong file gốc và tên trường, kể cả khi đã chia nhiều đợt nạp hoặc bỏ qua bài đánh dấu xóa. Ví dụ: **Bài 203 · trường content: thiếu nội dung bài**. Tool trở lại ô chọn file; sửa trường được chỉ ra trong JSON rồi nạp lại.

Lỗi hệ thống chưa có vị trí xác định vẫn được báo chung, không tự gán sang một ô không liên quan.
