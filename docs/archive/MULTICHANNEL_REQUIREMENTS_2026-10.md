# Yêu cầu mở rộng: lấy tin, phân phối đa kênh và lọc lead

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

**Cập nhật phạm vi sau khi chốt:** người dùng ưu tiên hoàn thiện Facebook; Threads/Zalo để sau, loại Zalo không còn là điều kiện để làm Facebook. Luồng nguồn JSON/JSON-LD và demo → đăng Facebook → lấy bình luận gắn căn/chiến dịch/nhóm đã được nối trong code; xem [phạm vi thực tế và hướng dẫn](../FACEBOOK_WORKFLOW.md). Các bảng đối chiếu bên dưới ghi hiện trạng tại thời điểm đề xuất trước thay đổi, không phải ma trận chức năng mới nhất.

Ngày chốt yêu cầu ban đầu: 29/10/2026. Đây là đặc tả cho giai đoạn tiếp theo, **chưa phải chức năng đã có trong EXE**.

## Mục tiêu và phạm vi hỗ trợ

Một tool cho phép lấy tin bất động sản từ nhiều nguồn, chọn tin/ảnh/nội dung, xem trước rồi đăng đến các đích người dùng đã kết nối; tiếp nhận phản hồi từ bài đã đăng và phân loại lead bằng registry hiện tại.

Không thể nghiệm thu bằng tiêu chí “mọi website, mọi link đều chạy”. Tiêu chí thực tế: thêm được website qua bộ kết nối (adapter), hiển thị rõ nguồn/kênh được hỗ trợ và những khả năng chưa hỗ trợ. URL đơn thuần không thay thế tài khoản, quyền truy cập, quyền đăng hoặc quyền đọc phản hồi.

Người dùng chưa có website mẫu và cho phép chọn nguồn. Chọn **website BĐS demo cục bộ với dữ liệu/ảnh mẫu do project cung cấp** làm nguồn kiểm thử đầu tiên. Đây là lựa chọn thiết kế, chưa triển khai website demo trong lần chốt yêu cầu này. Không lấy kết quả demo làm bằng chứng đã tích hợp một website bên ngoài. Website thật cần khảo sát API/HTML, quyền truy cập và kiểm thử riêng.

## Luồng sản phẩm

1. Thêm nguồn website: API hoặc kết nối trình duyệt/HTML được hỗ trợ; kiểm tra kết nối và xem trước trường dữ liệu nhận diện được.
2. Lấy danh sách tin và chi tiết/ảnh; lưu URL, ID nguồn và thời điểm lấy. Thiếu giá/diện tích/pháp lý thì ghi chưa có, không tự suy diễn.
3. Chọn tin, sửa nội dung và chọn ảnh. Xác nhận quyền sử dụng nội dung trước khi phân phối.
4. Kết nối tài khoản của từng kênh; chọn đúng nhóm/tài khoản/đích được hỗ trợ và có quyền đăng.
5. Xem trước riêng từng kênh vì giới hạn nội dung/ảnh có thể khác nhau. Bấm đăng để tạo chiến dịch chung, mỗi đích là một tác vụ độc lập.
6. Ghi kết quả từng đích: chưa gửi, đang gửi, đã đăng có bằng chứng, chờ duyệt, lỗi, cần thao tác hoặc chưa xác định. Lưu ID/URL bài hoặc ID tin nhắn để liên kết phản hồi.
7. Lấy bình luận/phản hồi có quyền truy cập từ bài/tin nhắn đã xác nhận. Tác vụ thu thập độc lập với tác vụ đăng, không coi “đăng thành công” là “đã lấy đủ phản hồi”.
8. Chuẩn hóa phản hồi → chống trùng → bộ lọc registry → lead tiềm năng/cần xem xét/bỏ qua. Nhân viên kiểm tra và xuất Excel; đồng bộ CRM là khả năng riêng cần tích hợp.

## Phương thức kết nối theo kênh

| Nguồn/kênh | Hướng triển khai | Điều kiện cần xác minh |
| --- | --- | --- |
| Website có API | Adapter ánh xạ endpoint, xác thực, phân trang, danh sách/chi tiết/ảnh về dữ liệu chung | Tài liệu API, quyền dùng dữ liệu, hạn mức và trường dữ liệu |
| Website có HTML có cấu trúc | Adapter đọc HTML/JSON-LD hoặc cấu hình selector theo domain; xem trước để xác nhận | Dữ liệu có thực sự nằm trong HTML, điều kiện sử dụng và độ ổn định |
| Website cần đăng nhập/render JavaScript | Adapter trình duyệt có profile riêng từng nguồn/khách | Luồng đăng nhập, quyền truy cập, cấu trúc DOM; không vượt CAPTCHA/xác minh |
| Facebook Groups | Dùng lại poster và phiên trình duyệt hiện có; nối bài xác nhận được với bộ lấy bình luận | Quyền nhóm, điều kiện nền tảng và nghiệm thu UI thật; chưa cam kết lấy đủ |
| Threads | Ưu tiên API chính thức cho tài khoản được ủy quyền, lưu ID bài và lấy replies theo quyền được cấp | Tài khoản/OAuth/app/quyền publish/read replies; cần xác minh loại đích người dùng muốn |
| Zalo | Chọn adapter sau khi chốt nhóm chat thông thường, OA/GMF hay nhật ký cá nhân | OA/GMF có API riêng; link mời nhóm thông thường không tự tương đương group_id/quyền OA |

Threads không được mặc định xử lý giống link nhóm Facebook. Với Zalo, phản hồi có thể là tin nhắn hội thoại; chỉ gắn với tin nguồn khi có reply/reference ID hoặc được người dùng xác nhận. Tin nhắn không rõ nguồn vào hàng chờ, không tự gắn vào căn vừa đăng gần nhất.

Tài liệu kiểm chứng:

- [Meta — Official Threads API workspace](https://www.postman.com/meta/threads/overview).
- [Zalo — gửi tin nhắn nhóm qua OA/GMF](https://docs.zaloplatforms.com/docs/OA/nhom-chat-gmf/tin-nhan/text_message): yêu cầu access token, group_id và quyền tương ứng; không chứng minh có thể gửi vào mọi nhóm bằng link mời.
- [Meta — How We Combat Scraping](https://about.fb.com/news/2021/04/how-we-combat-scraping/): phiên đăng nhập không thay thế sự cho phép thu thập tự động của nền tảng.

## Dữ liệu và hợp đồng kết nối cần xây

| Thành phần | Dữ liệu/trách nhiệm |
| --- | --- |
| SourceConnection | Domain, kiểu adapter, cấu hình mapping, tham chiếu thông tin xác thực; không lưu mật khẩu trong bài |
| SourceAdapter | Kiểm tra kết nối, danh sách tin, chi tiết tin, ảnh; khai báo có hỗ trợ đăng nhập/phân trang hay không |
| ListingSnapshot | source_id, external_id, source_url, title, description, giá/vị trí/diện tích nếu có, ảnh đã kiểm tra và hash nội dung |
| ChannelConnection | Khách, nền tảng, tài khoản được kết nối, capability publish/read_feedback, trạng thái xác thực |
| Destination | Nền tảng, account_id, loại đích, external_id/URL đã xác minh; không nhận mọi chuỗi link như một nhóm hợp lệ |
| DistributionCampaign/Task | Snapshot đã duyệt + nội dung từng kênh + trạng thái từng đích + mốc bắt đầu gửi + bằng chứng/ID kết quả |
| Publication | Nối tin nguồn với platform/account/destination và external_post_id hoặc message_id; một tin có thể có nhiều bài đã đăng |
| Feedback | Platform, external_feedback_id, publication_id nếu xác định được, external_author_id, nội dung, thời gian, URL, metadata gốc cần thiết |
| LeadAssessment | Phân loại, điểm, lý do, signals, registry_version và thông tin liên hệ; quyết định duyệt tay tách khỏi điểm tự động |

Chống trùng phản hồi bằng `(khách, nền tảng, tài khoản kết nối, external_feedback_id)`. Chống đăng trùng theo khách/tài khoản/đích/tin nguồn/phiên bản nội dung. Mốc gửi đã bắt đầu nhưng chưa xác nhận phải giữ unknown và yêu cầu kiểm tra, không tự gửi lại. Khóa riêng tài khoản/profile khi tự động thao tác trình duyệt.

Không gộp người dùng Facebook, Zalo, Threads chỉ vì trùng tên hoặc avatar. Gộp liên hệ cần định danh đã xác minh hoặc nhân viên xác nhận. Không suy ra số điện thoại khi phản hồi không cung cấp.

## Phân loại khách giữ như hiện tại

| Mức | Ý nghĩa |
| --- | --- |
| LEAD_POTENTIAL | Nhu cầu/liên hệ đủ tín hiệu quy tắc, cần sale xác nhận tiếp |
| NEEDS_REVIEW | Quan tâm sơ bộ hoặc chưa đủ rõ, chuyển xem xét |
| IGNORE | Spam, từ chối hoặc thiếu tín hiệu |

Dùng lại 5 registry hiện có: intent, variants, negation, spam, location. Điểm là điểm quy tắc, không phải xác suất; không tự đổi thành nóng/ấm/lạnh hoặc tuyên bố khách đã mua. Báo cáo cần giữ kênh, bài/tin nguồn, nội dung gốc, tác giả, liên hệ, điểm, lý do, trạng thái duyệt và thời điểm thu thập.

## Đối chiếu code hiện tại

| Chức năng | Hiện trạng |
| --- | --- |
| Lấy tin Revoland | Adapter theo hợp đồng giả định, có mock; chưa nghiệm thu API thật |
| Lấy tin website bất kỳ | Chưa có hệ thống adapter nguồn chung; demo nguồn mới cũng chưa được xây |
| Đăng nhóm Facebook | Có poster, phiên, campaign, chống trùng, retry, trạng thái; cần nghiệm thu Facebook thật |
| Đăng Zalo/Threads | Chưa có tích hợp |
| Lấy bình luận Facebook bằng URL | Có collector giới hạn và lịch sử; mới kiểm thử offline |
| Tự nối bài đã đăng với tác vụ lấy bình luận | Chưa có điều phối chung |
| Lọc ba mức, giải thích và Excel | Có và dùng lại được; báo cáo đa kênh cần thêm trường nguồn |

EXE FacebookLeadFilter hiện có không đáp ứng toàn bộ phạm vi mở rộng này. Kết quả 106 test trước đây chỉ xác minh bản hiện tại, không chứng minh các tích hợp tương lai.

## Thứ tự triển khai và nghiệm thu

1. Xây nguồn BĐS demo và SourceAdapter chung; thử thêm nguồn API/HTML cấu hình, chuẩn hóa và preview đủ dữ liệu/ảnh. Nguồn không hỗ trợ phải báo rõ.
2. Cho campaign Facebook nhận listing snapshot từ nguồn chung, bỏ ràng buộc chỉ Revoland; lưu Publication và tự tạo tác vụ thu thập theo ID/URL bài đã xác nhận.
3. Thêm Threads qua tài khoản/API được cấp quyền; thử đăng, lưu ID và lấy replies thật từ bài của tài khoản được ủy quyền.
4. Sau khi chốt loại Zalo, thử tính khả thi gửi/đọc phản hồi trên đúng loại đích rồi mới đưa vào luồng chung.
5. Hợp nhất bảng kết quả lead, chống trùng/duyệt tay/báo cáo; nghiệm thu đa kênh với mất phiên, gửi không xác định, giới hạn API, restart và dữ liệu trùng.
6. Build EXE mới sau khi các module được nối vào giao diện và vượt kiểm thử. Nghiệm thu mỗi website/kênh bằng bài thật, bằng chứng thật và tài khoản được phép sử dụng.

Đầu ra nghiệm thu phải kèm **ma trận nguồn/kênh hỗ trợ** có phương thức kết nối, phạm vi đăng/đọc phản hồi, ngày kiểm thử và giới hạn. Không ghi “hỗ trợ tất cả website” khi chưa có bằng chứng cho từng kết nối.

Thông tin còn thiếu: loại Zalo người dùng muốn (đã hỏi, đang chờ trả lời), loại đích Threads, tài khoản/quyền tích hợp thực tế. Không cần gửi mật khẩu, token hoặc cookie trong chat để chốt đặc tả.
