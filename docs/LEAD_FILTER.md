# Facebook Lead Filter — hướng dẫn sử dụng

## Bình luận không dấu (1.4.0)

Quy tắc đối chiếu cả có dấu và không dấu, kể cả khi viết lẫn hai kiểu. Ví dụ `mua`, `chot gia 2 ty`, `2 ty chot gia` được nhận là nhu cầu mua mạnh. Các câu `del mua`, `deo mua`, `khong mua`, `chua chot gia` vẫn được xử lý là từ chối; không cộng điểm mua từ phần bị phủ định. Bình luận gốc được giữ nguyên. Kết quả đã lưu dùng luật cũ được đánh giá lại khi mở bảng khách hàng hoặc xuất Excel.

**Cập nhật luồng tích hợp:** Dashboard chính `/` hiện là [Facebook Property Tool](FACEBOOK_WORKFLOW.md). Trang lọc lead độc lập trong tài liệu này ở `/leads`; có thể mở từ bài đã xác nhận đăng để giữ liên kết căn/chiến dịch/nhóm. Nguồn Revoland vẫn ở `/posting`.

Luồng chính: **Đăng nhập Facebook → nhập URL bài viết → lấy bình luận → lọc lead theo registry → xem kết quả → xuất Excel**. Không cần API Revoland cho luồng này. Công cụ đăng bài cũ vẫn tại `/posting`, dữ liệu khách cũ được giữ nguyên.

## Mở tool

Để dùng mã nguồn mới, chạy `run_tool.bat` khi đã có `.venv`. Hướng dẫn đầy đủ về chọn khách, cách mở và từng nút: [USER_GUIDE.md](USER_GUIDE.md).

Nhấp đúp `dist/FacebookLeadFilter.exe`, giữ cửa sổ console mở. Để dùng lại dữ liệu khách trước đây, chạy trong thư mục chứa EXE:

```powershell
.\FacebookLeadFilter.exe --customer khach01
```

Hoặc chạy mã nguồn trong terminal VS Code:

```powershell
.\start.ps1 -Customer khach01
```

Mở `http://127.0.0.1:8000`. EXE và `start.ps1` dùng cùng thư mục `%LOCALAPPDATA%\RevolandFBPoster\khach01`; tên thư mục cũ được giữ để dùng lại phiên. Nếu cổng đang bận, thêm `--port 8001` cho EXE hoặc `-Port 8001` cho PowerShell. Chỉ chạy một dashboard cho mỗi bộ dữ liệu khách.

## Hai tab chính

- **Đăng tin:** đăng và kiểm tra bài, lưu link bài đã đăng. Mở liên kết sang tab Khách hàng để lấy/lọc comment; không tự lấy sau đăng.
- **Khách hàng** (`/leads`): mặc định tổng hợp toàn bộ comment đã lưu, chỉ giữ bản mới nhất theo bài và mã comment. Cùng hồ sơ Facebook viết nhiều comment trên nhiều bài/nhóm được gom thành một khách hàng, giữ đầy đủ bình luận và nguồn. Mục Lấy & lọc comment nằm tại tab Khách hàng; chọn đợt đăng và một bài hoặc tất cả bài đã đăng. Excel xuất một sheet Khách hàng, mỗi khách một dòng. Lọc theo đợt đăng/nhóm/phân loại, tìm tên, điện thoại, Zalo, email hoặc nội dung. Bảng có 50 bản ghi/trang, hiển thị nhóm, đợt đăng và lần lấy gần nhất. **Tải Excel theo bộ lọc** xuất toàn bộ dữ liệu khớp mọi bộ lọc và ô tìm kiếm, kể cả trang khác.

Bấm **Xem kết quả** ở từng bài sẽ mở tab Khách hàng đúng đợt và bài đó; có nút xem các bài khác. Link xem cả đợt chỉ giới hạn theo đợt đăng. Bảng cập nhật khi có tác vụ đang chạy; **Làm mới** chỉ đọc dữ liệu đã lưu, không lấy Facebook.

**Lịch sử các lần lấy comment** được thu gọn riêng để xem snapshot cũ. **Quay lại kết quả tổng hợp** trở về dữ liệu mới nhất. Mở lại tool vẫn giữ lịch sử và kết quả; xem/xuất không đăng bài hay lấy comment.

## Công cụ bổ sung

Tab Khách hàng có mục **Công cụ bổ sung**, mặc định đóng:

1. **Lọc bài ngoài tool bằng link Facebook:** đăng nhập rồi dán link bài trực tiếp hoặc `/share/p/MA_CHIA_SE`, `/share/MA_CHIA_SE`. Tool tìm bài gốc qua chuyển hướng/metadata. Chọn 1–500 comment và bấm lấy; video/reel chưa hỗ trợ.
2. **Nhập comment thủ công / JSON:** dán mỗi comment một dòng hoặc tải JSON (tối đa 5 MB/5.000 bản ghi). Kết quả chưa lưu; tải Excel trước khi tải lại trang.
3. **Quy tắc phân loại:** xem registry và điểm để tham khảo.

Mỗi lần lấy lại cùng bài sẽ bổ sung comment mới và cập nhật comment đã đổi, giữ comment cũ chưa thấy ở lần này. Không xóa dữ liệu vì Facebook có thể ẩn/xếp hạng comment. Giới hạn 1–500 áp dụng mỗi bài trong mỗi lần lấy. Thời gian lấy tối đa **5 phút/bài** (tính cả mở link và điều hướng); dừng sớm nếu đạt giới hạn hoặc không có thêm dữ liệu. Hết thời gian trả kết quả một phần, giữ dữ liệu đã nhận; mỗi bài trong đợt có ngân sách riêng. **Dừng lấy comment** giữ dữ liệu đã nhận và không mở bài tiếp theo; thao tác điều hướng hiện tại có thể mất tối đa 45 giây.

## Trạng thái và giới hạn

| Trạng thái | Ý nghĩa |
| --- | --- |
| `running` | Đang đọc, lọc và lưu kết quả dần |
| `partial` | Có kết quả một phần: đạt giới hạn, hết thời gian/vòng hoặc không thấy thêm dữ liệu |
| `action_required` | Cần đăng nhập/xác minh, không truy cập được bài hoặc không nhận diện được bình luận |
| `stopped` | Đã dừng theo yêu cầu, giữ kết quả đã lấy |
| `failed` | Lỗi mạng/trình duyệt/DOM, giữ snapshot thành công gần nhất |
| `interrupted` | Tool bị đóng giữa chừng; đánh dấu khi mở lịch sử, giữ dữ liệu đã lưu |

Tool không khẳng định lấy đủ bình luận. Facebook có thể ẩn, xếp hạng hoặc giới hạn dữ liệu và thay đổi DOM. Luồng đã được kiểm thử bằng trang mô phỏng offline, **chưa nghiệm thu với tài khoản/bài viết Facebook thật**. Cần chạy thử trên bài mục tiêu trước khi sử dụng nghiệp vụ. Khi không nhận diện được cấu trúc bình luận, tool yêu cầu kiểm tra thay vì gán mọi văn bản trên trang thành bình luận.

Lead tiềm năng là kết quả quy tắc, cần nhân viên xác nhận nhu cầu. Tool chưa tạo/đồng bộ lead lên Revoland và không tự nhắn tin khách. Chống trùng theo bài và mã bình luận giữa các lần lấy; cùng một người viết nhiều comment vẫn là nhiều bản ghi. Comment không còn hiển thị ở lần lấy sau vẫn được giữ, vì tool không thể xác định comment bị xóa hay chỉ bị Facebook ẩn/xếp hạng.

Đăng nhập không tự cấp quyền thu thập dữ liệu tự động. Meta nêu việc tự động thu thập không có sự cho phép của họ vi phạm điều khoản: [How We Combat Scraping](https://about.fb.com/news/2021/04/how-we-combat-scraping/). Chỉ triển khai trong phạm vi được phép; tool dừng khi cần xác minh hoặc bị hạn chế truy cập.

## Hỏi thông tin và trả giá

Bộ luật 1.3.0 bổ sung các cách nói thường gặp:

- `xin hướng nhà`, `hướng ban công`, `hướng cửa`, `xin huong nha`: hỏi chi tiết, +25 điểm, **Cần xem lại** nếu đứng riêng.
- `2 tỷ mua luôn`, `2,5 tỷ chốt luôn`, `mua liền`, `cọc luôn`: cam kết mua/chốt, +40 điểm, **Khách tiềm năng** khi không có phủ định/spam.
- `fix giá`, `bớt được không`, `giá cuối cùng`, `có thương lượng`: thương lượng, +30 điểm, **Cần xem lại** nếu đứng riêng.

Các cụm cùng họ tín hiệu (`family`) chỉ lấy mức điểm cao nhất, kể cả khớp nhiều nhóm registry; không cộng lặp từ đồng nghĩa. Các câu `không mua luôn đâu`, `ko chốt luôn`, `không muốn chốt` vẫn bị loại, không cộng điểm mua cho phần bị phủ định.

## Luật phủ định và kết quả đã lưu

Bộ luật 1.3.0 nhận các cách viết tắt như `k muốn mua`, `ko muốn mua`, `hk muốn mua`, `khong muon mua`. Cụm ý định nằm trong phần phủ định không được cộng điểm mua/xem. Ví dụ `xấu vcl nhìn k muốn mua` là **Bỏ qua**, 0 điểm. Không suy ra ý định từ riêng cụm `muốn mua` bên trong lời từ chối.

Khi mở bảng tổng hợp, một lần lấy đã lưu hoặc xuất Excel, các kết quả từ bộ luật cũ được chấm lại theo luật hiện tại. Không ghi đè nội dung hay snapshot gốc trên đĩa. Nhãn/điểm của kết quả hiển thị có thể khác lúc thu thập vì đã sửa bộ lọc.

## Năm bảng registry

Đây là **file JSON quy tắc**, không phải bảng SQL hoặc Registry Windows. Xem đầy đủ quy tắc và điểm trong mục registry trên dashboard hoặc [danh sách chi tiết](REGISTRIES.md).

| File trong `core/registry/` | Vai trò | Nhóm |
| --- | --- | --- |
| `intent_registry.json` | Ý định mua, xem nhà, hỏi chi tiết, tư vấn, giá, khả dụng, tương tác, liên hệ | 10 |
| `variants_registry.json` | Từ viết tắt/biến thể: ib, qtam, pháp lý, đặc điểm, vị trí... | 9 |
| `negation_registry.json` | Từ chối mua/xem, chê giá/đặc điểm, nhu cầu khác, bình luận dạo | 6 |
| `spam_registry.json` | Quảng cáo vay, tuyển dụng, cờ bạc/crypto, dịch vụ, môi giới chen tin | 6 |
| `location_registry.json` | Tên và bí danh 23 khu vực; không cộng điểm | 23 |

Từ đồng nghĩa cùng họ tín hiệu chỉ tính điểm cao nhất. Phủ định/spam xét theo nhóm và các điều kiện ngữ cảnh; nhu cầu thuê/bán chuyển xem lại, không tự coi là spam. Số điện thoại +50; nếu không có thì xét Zalo +25; nếu không có Zalo thì email +30. Điểm là điểm quy tắc, không phải xác suất, có thể vượt 100. Spam phạt từ 100 bị bỏ qua ngay. Không có phủ định: SĐT hợp lệ là lead tiềm năng; điểm ≥40 còn cần ý định hành động hoặc ít nhất hai họ tín hiệu vừa/mạnh độc lập. Điểm ≥15 là cần xem xét. Tín hiệu yếu cộng lại không đủ để tự xác nhận lead. Phủ định có thể khiến bản ghi bị bỏ qua dù có liên hệ.

Sửa registry khi chạy source bằng cách chỉnh JSON tương ứng, giữ cấu trúc và chạy kiểm thử. EXE dùng registry đóng gói nên phải build lại để đổi quy tắc; chưa có chức năng sửa registry trên giao diện.

## Thử offline và lưu dữ liệu

Mở **Công cụ bổ sung → Nhập comment thủ công / JSON**, dùng dữ liệu mẫu, dán mỗi bình luận một dòng hoặc tải JSON (tối đa 5 MB/5.000 bản ghi). Kết quả nhập chỉ ở trang hiện tại, cần xuất Excel trước khi tải lại; luồng này không kiểm chứng thao tác Facebook thật.

Lịch sử nằm ở `data/lead_runs/*.json` trong thư mục khách, chứa nội dung, tên, URL liên quan, liên hệ và lý do phân loại. `profiles` chứa phiên Facebook. Không chia sẻ/đưa các thư mục này lên Git hoặc vào EXE. **Đăng xuất / xóa phiên** chỉ xóa phiên, không xóa lịch sử hay Excel đã tải.

## Mã nguồn

| Module | Chức năng |
| --- | --- |
| `services/facebook_comment_collector.py` | Kiểm tra URL, đọc DOM bài mục tiêu, mở thêm/cuộn có giới hạn |
| `services/lead_filter_service.py` | Tác vụ nền, khóa profile/đọc ghi, lưu lịch sử, dừng, lọc, liệt kê registry |
| `core/filter_engine.py` | Chuẩn hóa, khớp quy tắc, tính điểm, phân loại, giải thích |
| `core/contact_extractor.py` | Trích xuất điện thoại, Zalo và email |
| `api/server.py` | API `/api/leads/*`, phiên Facebook dùng chung, tải XLSX |
| `api/static/leads.*` | Giao diện chính với CSS/JS cục bộ, không cần CDN |

Các module thử nghiệm cũ `BrowserLeadManager` và `CommentPipeline` không được nối vào luồng mới. Phiên và khóa trình duyệt dùng chung với công cụ đăng bài để tránh mở hai trình duyệt cùng profile.

## Mức độ quan tâm, DM và comment ẩn danh (1.3.0)

Mỗi nhóm từ trong registry có mức độ (`strength`) riêng, không suy ra mức độ chỉ từ tổng điểm hoặc SĐT:

| Mức | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Mạnh | cần mua, mua luôn, chốt/cọc, hẹn xem | Có ý định hành động |
| Vừa | xin hướng nhà, hỏi pháp lý, xin tư vấn, DM me the price, rất quan tâm | Hỏi sâu hoặc yêu cầu trao đổi |
| Yếu | ib, hỏi giá, quan tâm sơ bộ, đẹp quá | Tín hiệu sơ bộ; lời khen không tự thành lead |
| Chưa rõ | dm đứng riêng, tín hiệu mâu thuẫn, nội dung bị cắt ngắn | Cần kiểm tra ngữ cảnh |
| Chưa thấy nhu cầu | không có tín hiệu, phủ định hoặc spam | Xem lý do cụ thể |

Mức quan tâm và phân loại lead là hai thông tin riêng; phân loại vẫn xét điểm, phủ định, spam và độ đầy đủ nội dung. Bảng Khách hàng có bộ lọc mức độ, hiển thị cụm từ làm căn cứ. Excel áp dụng cả bộ lọc mức và có các cột mức/cụm từ/loại tác giả/kênh liên hệ.

`dm` không nằm trong danh sách tự cộng điểm hay tự coi là chửi. `DM me`/`please DM me details` là yêu cầu nhắn tin; `dm` đứng riêng cần xem lại. `dm giá cao thế` xét lời chê giá; `dm đẹp quá, 2 tỷ mua luôn` vẫn xét nhu cầu mua. `đừng DM tôi`/`don't DM me` không cộng điểm nhắn tin. Có nhu cầu mua nhưng từ chối DM là trường hợp cần xem lại. Không đoán quốc tịch/ngôn ngữ từ tên hoặc hồ sơ.

Comment ẩn danh có permalink đúng bài vẫn được lấy và phân loại theo nội dung. Nhãn ẩn danh được giữ; nếu không đọc được tác giả thì ghi Chưa xác định tác giả, không tự coi là ẩn danh và không tạo link hồ sơ. Không gộp nhiều người vì cùng tên Ẩn danh: chống trùng theo bài và mã comment. Kênh liên hệ tách riêng thành SĐT/Zalo/email/hồ sơ/comment/chưa có; thiếu hồ sơ không tự hạ mức nhu cầu. Comment từng bị bỏ sót do không có link tác giả cần bấm lọc lại để thu thập.

## Bổ sung từ nguồn registry bổ sung (1.3.0)

Đã đối chiếu 5 file người dùng cung cấp. Xem [các trường hợp được nhập và điều chỉnh ngữ cảnh](REGISTRY_IMPORT_REVIEW.md), gồm liên hệ hợp lệ, tiêu chí căn nhà, hỏi pháp lý/đường vào/vị trí, thuê/bán khác nhu cầu, quảng cáo chen tin và câu hỏi vay.
