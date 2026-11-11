# Hướng dẫn sử dụng Revoland Facebook Poster

> Tài liệu lưu trữ trước đợt sắp xếp 02/11/2026. Nội dung và số dòng mô tả phiên bản cũ; xem [kiến trúc hiện tại](../ARCHITECTURE.md) và [báo cáo rà soát](../PROJECT_REVIEW.md).

**Cập nhật 29/10/2026:** Giao diện chính đã chuyển sang lọc lead. Đọc [hướng dẫn Facebook Lead Filter](../LEAD_FILTER.md) để lấy bình luận từ URL bài Facebook, lọc theo registry và xuất Excel. Tài liệu dưới đây mô tả công cụ đăng bài cũ ở `/posting`. EXE mới là `dist/FacebookLeadFilter.exe`.

**Ngày cập nhật:** 28/10/2026  
**Đối tượng:** khách sử dụng tool trên Windows, người chạy bằng VS Code và người hỗ trợ bàn giao.

## 1. Đọc trước khi bắt đầu

Tool hỗ trợ chọn căn, xem trước nội dung/ảnh, chọn nhóm và thao tác đăng lần lượt bằng phiên Facebook của khách. Bạn tự nhập mật khẩu và mã xác thực trực tiếp trên Facebook; phiên còn hiệu lực được dùng lại cho lần sau.

**Tình trạng của bản hiện tại:**

| Nội dung | Hiện trạng |
|---|---|
| Lấy căn từ API Revoland | Đã có adapter; endpoint và dữ liệu API thật chưa được nghiệm thu |
| Xem căn mẫu khi chưa có API | Có; chỉ dùng thử giao diện |
| Đăng nhập và sử dụng phiên Facebook | Đã có luồng; cần nghiệm thu với tài khoản/nhóm mục tiêu |
| Thêm/chọn nhóm, preview, lịch sử, retry | Đã có |
| Đọc danh sách tin Revoland bằng phiên trình duyệt thay API | **Chưa có trong luồng dashboard**; đây mới là hướng đã trao đổi |
| Dán link tin Revoland để tool tự lấy bài | Chưa có chức năng này trên dashboard |
| Đăng một bài tự nhập bất kỳ, không chọn căn | Chưa có luồng riêng; hiện phải chọn một căn làm nguồn |
| Lọc/xuất file bình luận hoặc lead JSON | Có mục nhập JSON và tải Excel; không gọi API tạo lead |
| Tự thu thập bình luận và tạo lead thật trên dashboard | Chưa triển khai; code thử nghiệm nằm ngoài MVP |

**Nếu bạn chưa có API:** làm phần cài đặt, chạy chế độ mẫu, quản lý nhóm và kiểm thử tự động trong hướng dẫn này. Chế độ mẫu không cho đăng Facebook thật. Chỉ đăng nhập Revoland trên Chrome hiện tại chưa làm dashboard tự lấy được căn.

Hai lỗi P1 được ghi nhận trước đây đã được sửa. Các giới hạn khác vẫn nằm trong [báo cáo review](CODE_REVIEW_2026-10-28.md). Kiểm thử tự động không thay cho nghiệm thu trên API và nhóm thật.

## 2. Chuẩn bị

Bạn cần:

- Máy Windows và thư mục project đầy đủ.
- Python 3.12 trở lên; có Python Launcher `py` nếu dùng script cài đặt.
- VS Code nếu muốn chạy qua Terminal tích hợp.
- Internet để cài thư viện/Chromium; khi vận hành cần truy cập được Revoland, ảnh và Facebook.
- Tài khoản Facebook của chính khách, có thể hoàn tất OTP/xác minh.
- Link các nhóm mà tài khoản được phép đăng bài.
- Nếu chạy với căn thật: API URL, phương thức xác thực và dữ liệu phù hợp adapter.

Không gửi mật khẩu Facebook, OTP, API key hoặc thư mục phiên cho người khác khi nhờ hỗ trợ.

## 3. Cài đặt lần đầu trong VS Code

### 3.1. Mở đúng thư mục

1. Mở VS Code.
2. Chọn **File → Open Folder**.
3. Mở thư mục `tool_lead_fb`, nơi có `cli.py`, `install.ps1`, `start.ps1` và `requirements-lock.txt`.
4. Chọn **Terminal → New Terminal**; dùng PowerShell.

Kiểm tra Terminal đang ở đúng project:

```powershell
Get-Location
Test-Path .\cli.py
```

Lệnh thứ hai phải trả `True`. Không chạy các lệnh bên dưới khi Terminal đang ở thư mục cha hoặc thư mục khác.

### 3.2. Cài bằng script

```powershell
.\install.ps1
```

Script tạo `.venv` nếu chưa có, cài thư viện theo phiên bản đã khóa và tải Chromium của Playwright. Khi thành công sẽ hiện hướng dẫn chạy `start.ps1`.

Chỉ cần cài lần đầu hoặc cài lại khi môi trường bị thiếu/hỏng. Không cần chạy install mỗi lần sử dụng.

### 3.3. Nếu script PowerShell bị chặn

Bạn có thể cài từng bước bằng lệnh Python, không cần thay đổi chính sách PowerShell toàn máy:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Nếu máy chưa có lệnh `py`, cần cài/chọn Python phù hợp trước. Nếu đã có `.venv` hoạt động, không cần tạo lại nó.

## 4. Khởi động và dừng tool

### 4.1. Cách nên dùng: chọn tên khách cố định

Trong Terminal project:

```powershell
.\start.ps1 -Customer khach01
```

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000).

Tên `khach01` là tên thư mục dữ liệu, không phải tài khoản đăng nhập website. Có thể thay bằng tên dễ nhớ không dấu, dùng chữ/số/gạch ngang/gạch dưới, dài 1–48 ký tự. Các lần sau dùng lại đúng tên này để giữ cấu hình, nhóm, lịch sử và phiên.

Script lưu dữ liệu ở:

```text
%LOCALAPPDATA%\RevolandFBPoster\khach01
```

Bạn có thể dán đường dẫn đó vào thanh địa chỉ File Explorer. Script còn thiết lập quyền truy cập cho thư mục khách; nếu bước thiết lập quyền báo lỗi thì script sẽ dừng.

### 4.2. Chạy trực tiếp bằng Python trong VS Code

```powershell
.\.venv\Scripts\python.exe cli.py --server
```

Lệnh trên dùng thư mục `REVOLAND_DATA_DIR` nếu Terminal đã đặt biến này. Nếu chưa đặt, nó dùng dữ liệu trong thư mục project. Vì vậy đổi qua lại giữa cách này và `start.ps1` có thể khiến bạn thấy “mất cấu hình/phiên” dù thực tế đang mở bộ dữ liệu khác.

Nếu cần chạy Python trực tiếp nhưng vẫn dùng dữ liệu của `khach01`, đặt rõ thư mục trước:

```powershell
$env:REVOLAND_DATA_DIR = "$env:LOCALAPPDATA\RevolandFBPoster\khach01"
.\.venv\Scripts\python.exe cli.py --server --port 8000
```

Cách thủ công này không tự thực hiện bước thiết lập quyền thư mục như `start.ps1`. Khi có thể, dùng nhất quán script theo tên khách.

### 4.3. Nếu cổng 8000 đã được sử dụng

```powershell
.\start.ps1 -Customer khach01 -Port 8001
```

Mở [http://127.0.0.1:8001](http://127.0.0.1:8001). Đổi cổng không đổi khách; đổi tên khách sẽ đổi bộ dữ liệu.

Để phục vụ khách khác, dùng tên khác và cổng khác. Không mở hai bản cho cùng khách để thao tác song song trên cùng profile.

### 4.4. Dừng tool

Đợi chiến dịch hoàn tất hoặc dừng để cần can thiệp. Quay về Terminal đang chạy server và nhấn **Ctrl+C**. Giữ cửa sổ Terminal mở trong khi sử dụng; đóng tab dashboard không đồng nghĩa worker đăng bài đã dừng.

Hiện chưa có nút hủy chiến dịch trên giao diện. Nếu buộc phải dừng khi đang gửi, sau khi mở lại hãy kiểm tra lịch sử và nhóm Facebook trước khi thử lại.

## 5. Nhận biết các khu vực trên giao diện

| Khu vực/nút | Công dụng |
|---|---|
| Cấu Hình API Revoland | Đổi nguồn căn, key, chế độ mẫu, liên hệ và khoảng nghỉ |
| Banner chế độ dữ liệu | Cho biết đang xem dữ liệu mẫu hay dữ liệu API thật |
| Phiên Trình Duyệt Facebook Của Khách | Xem trạng thái, mở login, kiểm tra lại hoặc xóa phiên |
| Chọn Căn Đã Đăng Trên Revoland | Tải danh sách và chọn căn nguồn |
| Chọn Nhóm Facebook Mục Tiêu | Thêm/import nhóm và tick nhóm muốn đăng |
| Xem trước | Kiểm tra/sửa nội dung và xem danh sách ảnh |
| Bắt đầu đăng bài | Tạo chiến dịch và khởi chạy đăng lần lượt |
| Kết quả từng nhóm | Xem trạng thái, link, ghi chú, số lần retry và thời gian |
| Lịch sử | Mở lại chiến dịch trước đó |
| Xuất chiến dịch đang xem / Xuất toàn bộ lịch sử | Tải Excel kết quả đăng từng nhóm |
| Xuất bình luận / lead ra Excel | Nhập JSON để lọc liên hệ/phân loại và tải Excel |

## 6. Chưa có API Revoland: dùng thử như thế nào?

1. Mở **Cấu Hình API Revoland**.
2. Bật **Chế Độ Giả Lập (Mock Mode)**.
3. Kiểm tra tên và số liên hệ trong form; đổi nếu muốn thử nội dung định dạng.
4. Bấm **Lưu Cấu Hình**.
5. Quan sát banner **DỮ LIỆU MẪU** và các căn mẫu.
6. Chọn từng căn, đọc/sửa nội dung preview và xem ảnh.
7. Thử thêm/import/chọn nhóm theo phần 9.

Ảnh mẫu là URL bên ngoài; có thể không tải được khi mạng hoặc nguồn ảnh gặp lỗi. Mock mode không đồng nghĩa mọi tài nguyên đều nằm sẵn trên máy.

**Kết quả mong đợi:** xem được luồng chọn căn/nhóm/preview; nút đăng bị khóa. Đó là hành vi chủ động để không đưa căn mẫu lên nhóm thật. Chỉ sửa chữ trong preview của căn mẫu không biến nó thành một căn live.

Bạn vẫn có thể thử đăng nhập/kiểm tra/xóa phiên Facebook mà chưa có API. Đây là tài khoản và phiên thật; khác với bài test Chromium giả lập ở phần 16.

## 7. Khi đã có API: cấu hình nguồn căn thật

1. Mở **Cấu Hình API Revoland**.
2. Nhập **Revoland API URL** do bên cung cấp xác nhận.
3. Nhập **Revoland API Key** nếu API dùng đúng kiểu key mà adapter hỗ trợ.
4. Bỏ chọn **Chế Độ Giả Lập**.
5. Nhập đúng **Số Điện Thoại Đính Kèm Bài** và **Tên Chuyên Viên Tư Vấn**.
6. Đặt khoảng nghỉ tối thiểu/tối đa; tối thiểu không được lớn hơn tối đa. Mặc định là 5–10 giây.
7. Bấm **Lưu & Kiểm Tra Kết Nối**. Nút này lưu thay đổi trước khi kiểm tra.
8. Khi kết nối thành công, kiểm tra danh sách căn đã tải lại; nếu cần bấm **Tải lại**.

Key đã lưu không hiển thị lại trong form. Để trống ô key nghĩa là giữ key cũ; không phải xóa key. Bấm **Hủy** sau khi đã bấm nút lưu/kiểm tra không hoàn tác cấu hình vừa lưu.

Adapter hiện giả định `/ping`, `/listings?page=N` và Bearer key. Thành công ở ping chưa bảo đảm danh sách/ảnh đúng. Nếu endpoint, kiểu xác thực hoặc JSON Revoland khác, cần chỉnh adapter. Không tự lấy URL trang chủ, link chi tiết căn hoặc một request Network bất kỳ để coi là API tương thích.

Khoảng nghỉ giúp giãn các thao tác. Không có khoảng nghỉ nào bảo đảm tài khoản không bị Facebook yêu cầu xác minh hoặc hạn chế.

## 8. Đăng nhập Facebook

1. Bấm **Mở Trình Duyệt Đăng Nhập FB**.
2. Đợi cửa sổ Chromium xuất hiện trên máy chạy tool.
3. Tự nhập tài khoản, mật khẩu và OTP trực tiếp trên Facebook.
4. Hoàn tất các bước xác minh mà Facebook yêu cầu.
5. Đợi tool xác nhận và đóng cửa sổ; xem trạng thái trên dashboard.
6. Nếu cần, bấm **Kiểm Tra Lại** sau khi hoàn tất.

Dashboard chờ quá trình login tối đa khoảng 180 giây sau khi trang được mở. Nếu quá thời gian hoặc bạn đóng cửa sổ trước khi hoàn tất, mở lại và thử tiếp. Tool không yêu cầu lưu mật khẩu vào dashboard.

**Phải đăng nhập trong cửa sổ tool mở.** Việc bạn đã đăng nhập trên Chrome thông thường không tự cấp phiên đó cho tool. Khi đang login, không mở thêm login nhiều lần hoặc yêu cầu xóa phiên.

Lần sử dụng sau, khởi động đúng tên khách và kiểm tra phiên. Nếu còn hiệu lực thì dùng tiếp; nếu hết phiên/checkpoint thì đăng nhập hoặc xác minh lại. Có thể thấy trạng thái bận khi một thao tác khác đang giữ trình duyệt; hãy đợi rồi kiểm tra lại.

## 9. Thêm và chọn nhóm

### 9.1. Chuẩn bị link nhóm

Mở nhóm trên Facebook và copy URL trang nhóm. Dùng link dạng:

```text
https://www.facebook.com/groups/ID_HOAC_TEN_NHOM
```

Đoạn trên là cấu trúc minh họa; thay bằng nhóm thực tế của bạn. Không dùng link bài viết có `/posts/...`, link mời rút gọn hoặc trang cá nhân.

Tài khoản cần đã tham gia nhóm và có quyền đăng. Thêm URL vào tool không tự tham gia, không tự trả lời câu hỏi xét duyệt và không cấp thêm quyền.

### 9.2. Thêm một nhóm

1. Bấm **+ Thêm nhóm**.
2. Nhập **Tên Nhóm Facebook** dễ nhận biết.
3. Dán **Đường Dẫn URL Nhóm**.
4. Điền **Khu Vực / Phân Loại** nếu muốn.
5. Để ô nhập nhanh danh sách link trống.
6. Bấm **Xác Nhận Thêm**.

Nhóm được chuẩn hóa URL và kiểm tra trùng. Thông tin được giữ lại khi mở tool bằng cùng tên khách.

### 9.3. Import nhiều nhóm

1. Mở **+ Thêm nhóm**.
2. Dán các URL nhóm thực vào ô **Dán Nhanh Danh Sách Link Nhóm**, mỗi dòng một link.
3. Bấm **Xác Nhận Thêm**.
4. Kiểm tra thông báo số nhóm mới và xem lại tên/link trong bảng.

Khi ô nhập nhanh có nội dung, tool ưu tiên import, không dùng đồng thời các ô thêm một nhóm. URL trùng được bỏ qua; dòng không nhận diện được URL nhóm có thể không được nhập. Link sai đường dẫn cần sửa trước khi dùng.

### 9.4. Chọn nhóm để đăng

Tick đúng các nhóm cần đăng; có thể dùng **Chọn tất cả** hoặc **Bỏ chọn**. Nhóm mới tải lên không tự tick sẵn. Xem lại danh sách trước khi bấm đăng.

**Xóa** chỉ gỡ nhóm khỏi danh sách tool. Nó không rời nhóm Facebook, không xóa bài đã đăng và không xóa lịch sử chống trùng.

## 10. Chọn căn và kiểm tra preview

1. Tại danh sách căn, chọn đúng căn muốn đăng.
2. Đọc toàn bộ tiêu đề, giá, diện tích, vị trí, phòng ngủ/phòng tắm và pháp lý.
3. Kiểm tra mô tả, tên liên hệ, số điện thoại và link chi tiết.
4. Chỉnh nội dung trong ô preview nếu cần.
5. Kiểm tra mọi ảnh hiển thị đúng căn.
6. Kiểm tra lại các nhóm đã tick.

Giao diện hiện không có bộ chọn/xóa riêng từng ảnh để gửi một phần; backend tải toàn bộ ảnh của căn. Nếu cần thay ảnh nguồn, sửa trên hệ thống nguồn rồi tải lại căn và kiểm tra lại.

Đừng coi các thông số tự điền là đã được xác minh: schema còn giá trị mặc định khi API thiếu trường. Không bấm đăng nếu thông tin sai hoặc chưa rõ. Preview ảnh hiện dựa trên URL nguồn, chưa khóa bytes ảnh ngay lúc xem; nếu nguồn vừa cập nhật ảnh thì tải lại preview trước khi xác nhận.

Nếu báo dữ liệu căn đã thay đổi, tải lại căn và duyệt lại nội dung. Việc chọn lại căn/tải lại sẽ điền lại preview và có thể làm mất phần sửa chưa gửi; lưu bản nháp nội dung ở nơi riêng nếu cần.

## 11. Khởi chạy đăng bài

Điều kiện để nút đăng hoạt động: đang dùng dữ liệu live, phiên Facebook hợp lệ, đã chọn căn và không có thao tác bận. Ngoài ra phải tick ít nhất một nhóm và có nội dung hợp lệ.

1. Bấm **BẮT ĐẦU ĐĂNG BÀI LÊN CÁC NHÓM** một lần.
2. Tool kiểm tra nguồn căn và tải ảnh; một ảnh lỗi sẽ chặn tạo chiến dịch.
3. Khi chiến dịch bắt đầu, bảng kết quả xuất hiện và cập nhật từng nhóm.
4. Để Terminal/server tiếp tục chạy. Không thao tác vào ô soạn bài hoặc cửa sổ Facebook mà tool đang điều khiển.
5. Gặp cần xác minh hoặc chưa rõ kết quả, tool dừng các nhóm sau để bạn xử lý.

Tool không yêu cầu đăng nhập lại cho từng nhóm nếu phiên còn hợp lệ. Những nhóm đã đăng/đang chờ duyệt cho cùng căn sẽ được bỏ qua theo lịch sử, kể cả khi bạn xóa rồi thêm lại cùng URL nhóm.

Tạo campaign mới hoặc thay nội dung preview không tự bỏ cơ chế chống trùng. Hiện chưa có tính năng “ép đăng lại nhóm đã thành công”; không xóa lịch sử để né kiểm tra.

## 12. Hiểu bảng kết quả

| Hiển thị / mã | Ý nghĩa | Bạn cần làm gì? |
|---|---|---|
| Chưa gửi / pending | Nhóm chưa được xử lý | Đợi hoặc dùng nút tiếp tục khi đã xử lý nguyên nhân dừng |
| Đang thao tác / running | Tool đang làm việc trên nhóm | Chờ; chưa coi là thành công |
| Đã xác nhận đăng / posted | Engine có bằng chứng bài mới hoặc khách đã xác minh | Bấm Xem bài đăng và đối chiếu nội dung/ảnh |
| Chờ duyệt / pending_approval | Có xác nhận bài chờ quản trị viên | Kiểm tra hàng chờ trên Facebook; không đăng lặp |
| Thất bại trước gửi / failed | Có lỗi trước gửi, hoặc khách xác nhận chưa gửi/bị từ chối | Xem lý do rồi mới retry |
| Cần thao tác / action_required | Phiên/quyền cần xử lý hoặc browser bận | Hoàn tất thao tác, kiểm tra phiên rồi retry |
| Chưa rõ kết quả / unknown | Có thể đã gửi nhưng chưa xác nhận được | Kiểm tra nhóm và xác nhận theo phần 13 |
| Bỏ qua trùng / skipped_duplicate | Cùng căn đã đăng/đang duyệt ở cùng nhóm | Không có lần gửi mới cho task này |

Cột **Số Lần Retry** đếm lần thử lại của task. **Thời Gian** là thời điểm ghi nhận/xác nhận kết quả, không phải cam kết giờ Facebook xuất bản bài.

Trạng thái chiến dịch là tổng hợp. `completed` có thể bao gồm bài chờ duyệt hoặc nhóm bỏ qua trùng; `paused` cần tiếp tục/xử lý; `needs_review` có task unknown; `interrupted` là lần chạy bị gián đoạn.

## 13. Xử lý unknown, chờ duyệt, retry và tiếp tục

### 13.1. Khi chưa rõ kết quả

1. Mở đúng nhóm bằng đúng tài khoản Facebook.
2. Tìm bài của bạn trên nhóm và kiểm tra cả mục bài chờ duyệt nếu nhóm hỗ trợ.
3. Khi chiến dịch không còn chạy, bấm **Kiểm tra và xác nhận** ở task tương ứng.
4. Hộp thoại cho ba lựa chọn:

| Nhập | Dùng khi | Bước tiếp theo |
|---|---|---|
| `1` | Bài đã đăng | Dán permalink đúng bài/nhóm, rồi xác nhận |
| `2` | Bài đang chờ duyệt | Xác nhận bạn đã kiểm tra trên Facebook |
| `3` | Chắc chắn chưa gửi hoặc bài bị từ chối | Xác nhận cho phép task có thể thử lại |

Nếu vẫn không biết bài đang ở đâu, hủy hộp thoại và tiếp tục kiểm tra; không chọn `3` chỉ để làm nút retry xuất hiện.

Permalink là link **bài viết**, không phải link nhóm. Cấu trúc được tool nhận:

```text
https://www.facebook.com/groups/ID_HOAC_TEN_NHOM/posts/ID_BAI
https://www.facebook.com/groups/ID_HOAC_TEN_NHOM/permalink/ID_BAI
```

Dùng ID thật; link phải trỏ đúng nhóm của task. Nếu link chia sẻ Facebook có dạng khác, mở bài trực tiếp và lấy permalink phù hợp. Tool kiểm tra cấu trúc link khi bạn xác nhận, không tự chứng thực toàn bộ nội dung bài đó.

### 13.2. Khi bài đang chờ duyệt

Không retry một bài đang chờ duyệt. Sau khi admin duyệt, có thể dùng **Kiểm tra và xác nhận**, chọn `1` và dán permalink. Nếu bài bị từ chối, kiểm tra lý do/quy định nhóm trước khi chọn `3` để cho phép xử lý lại.

Tool chưa tự theo dõi định kỳ việc admin duyệt hoặc từ chối bài.

### 13.3. Thử lại các nhóm thất bại

1. Xử lý nguyên nhân: phiên, quyền đăng, mạng hoặc giao diện.
2. Kiểm tra không còn task unknown chưa xác minh trong chiến dịch.
3. Bấm **Thử Lại Các Nhóm Thất Bại**.
4. Tool chỉ chọn failed/action_required; không gửi lại posted/pending_approval.

### 13.4. Tiếp tục nhóm chưa gửi

Dùng **Tiếp tục nhóm chưa gửi** khi chiến dịch còn pending sau khi dừng. Lệnh này cũng có thể xử lý các task failed/action_required còn đủ điều kiện, không chỉ pending. Xác minh mọi unknown trước khi tiếp tục.

## 14. Mở lịch sử và dùng lại ở lần sau

1. Khởi động bằng đúng tên khách/cổng.
2. Mở dashboard và kiểm tra phiên Facebook.
3. Tại **Lịch sử**, chọn chiến dịch muốn xem.
4. Đối chiếu từng nhóm, permalink, ghi chú và retry_count.

Tải lại trang vẫn giữ lịch sử; nếu campaign đang chạy, dashboard sẽ theo dõi lại. Không đổi lựa chọn lịch sử trong khi một campaign đang được theo dõi là đang chạy.

Khi app bị đóng giữa chừng, lần mở lại sẽ phục hồi trạng thái: task đã bắt đầu gửi nhưng chưa có kết quả phải kiểm tra; task dừng trước bước gửi có thể thử lại. Không có cơ chế tự khởi chạy lại toàn bộ chiến dịch sau restart.

## 15. Đăng xuất, dữ liệu và sao lưu

### 15.1. Xóa phiên Facebook

1. Đợi campaign hoàn tất/dừng và đóng hoặc hoàn tất login.
2. Bấm **Xóa Phiên / Đăng Xuất**.
3. Xác nhận và kiểm tra thông báo kết quả.

Xóa phiên chỉ xóa dữ liệu browser cục bộ của khách; không xóa cấu hình Revoland, danh sách nhóm, lịch sử hoặc bài trên Facebook. Để thu hồi phiên phía Facebook, dùng phần mật khẩu/bảo mật của tài khoản Facebook.

### 15.2. Tìm dữ liệu khách

| Thành phần | Đường dẫn bên trong thư mục khách |
|---|---|
| Cấu hình và key | config/config.json |
| Danh sách nhóm | config/groups.json |
| Lịch sử | data/campaigns.sqlite3 |
| Ảnh chiến dịch | data/temp_images/ |
| Phiên Facebook | profiles/fb_user_profile/ |

Khi cần sao lưu, dừng server và đóng mọi browser của tool trước. Giữ lịch sử cùng ảnh mà các campaign chưa hoàn tất đang tham chiếu. Không tự sửa SQLite hoặc xóa ảnh đang dùng để khắc phục một task lỗi.

Ảnh snapshot chưa có cơ chế dọn tự động. Khi dung lượng tăng, nhờ người quản trị xác định ảnh không còn được dùng trước khi dọn. Profile là dữ liệu nhạy cảm; không đưa lên Git/đám mây hoặc sao chép cho người khác. Chuyển profile sang máy khác không bảo đảm phiên còn dùng được; có thể phải login lại.

## 16. Chạy kiểm thử khi chưa có API hoặc tài khoản thử

Các test tự động dùng dữ liệu riêng và dịch vụ giả lập. Không cần API key Revoland hoặc phiên Facebook thật; browser test vẫn cần Chromium đã cài.

Cài thư viện kiểm thử:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Chạy toàn bộ:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Chạy riêng từng phần:

```powershell
# Revoland: response, phân trang, lỗi API và ảnh
.\.venv\Scripts\python.exe -m pytest tests/test_revoland.py -v

# Chiến dịch, chống trùng, retry và phục hồi
.\.venv\Scripts\python.exe -m pytest tests/test_campaign.py -v

# Nhóm và phiên
.\.venv\Scripts\python.exe -m pytest tests/test_groups.py tests/test_session.py -v

# Giao diện và thao tác browser qua trang giả lập
.\.venv\Scripts\python.exe -m pytest tests/test_browser.py -v

# Bỏ qua các bài kiểm thử Chromium
.\.venv\Scripts\python.exe -m pytest -m "not browser" -q
```

Lần chạy được ghi nhận gần nhất: **89 passed, 1 warning**, bao gồm kiểm thử xuất file và cấu hình bản EXE. `passed` là test qua; `failed` cần đọc tên test/traceback; warning deprecation đã ghi trong [báo cáo kiểm thử](VERIFICATION_2026-10.md). Test không chứng minh mọi giao diện Facebook thật đều tương thích.

## 17. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy cli.py hoặc lệnh không tìm được file | Mở đúng thư mục project trong VS Code; kiểm tra Get-Location và Test-Path |
| Không có .venv\Scripts\python.exe | Cài môi trường theo phần 3 |
| ModuleNotFoundError | Dùng đúng Python trong .venv và cài requirements-lock.txt; với pytest cài thêm requirements-dev.txt |
| Playwright báo thiếu executable | Chạy lệnh cài Chromium ở phần 3/16 bằng đúng Python .venv |
| Không vào được dashboard | Kiểm tra Terminal còn chạy, startup có thành công và URL dùng đúng cổng |
| Cổng đã được sử dụng | Dừng đúng bản server cũ hoặc chọn cổng khác; không đóng ngẫu nhiên ứng dụng khác |
| Mở lại nhưng không thấy nhóm/phiên cũ | Kiểm tra tên khách và REVOLAND_DATA_DIR, xem có đổi giữa start.ps1 và chạy Python trực tiếp không |
| Nút đăng bị khóa | Kiểm tra mock mode, phiên hợp lệ, căn đã chọn và thao tác đang bận; muốn đăng thật cần nguồn căn live |
| API báo 401/403 | Kiểm tra key và quyền truy cập; không đổi sang dữ liệu mẫu rồi coi đó là kết nối thật |
| Ping được nhưng không tải được căn | Endpoint danh sách, phân trang hoặc JSON chưa khớp adapter; cần tài liệu/response đã che dữ liệu nhạy cảm |
| Không có căn | Kiểm tra dữ liệu/quyền/trạng thái trên nguồn và bấm tải lại; danh sách rỗng không tự thay bằng mẫu |
| Không tải được ảnh | Kiểm tra URL và quyền tải từ máy chạy tool; ảnh trên 20 MB hoặc file không đọc được sẽ bị chặn |
| Browser không mở hoặc tự đóng trước khi login xong | Kiểm tra Chromium, mạng và thời gian chờ; mở lại, không bấm login liên tục |
| Phiên cần xác minh/checkpoint | Hoàn tất trực tiếp trong browser tool, sau đó kiểm tra lại; không tự động vượt bước xác minh |
| Browser/profile đang bận | Đợi tác vụ đang chạy, tránh mở hai tool cùng khách; không xóa file lock/profile thủ công |
| Không tìm được ô đăng/nút đăng | Kiểm tra đã tham gia, có quyền đăng và giao diện nhóm; nếu vẫn lỗi cần cập nhật selector |
| Chưa xác nhận tải đủ ảnh | Không gửi bài; kiểm tra tải ảnh, giao diện attachment và mạng; không vô hiệu hóa kiểm tra để gửi thiếu ảnh |
| Composer có ảnh draft cũ | Đợi tool dừng, kiểm tra/xóa bản nháp trên Facebook. Nếu draft vẫn còn trong profile của tool, nhờ hỗ trợ thao tác đúng profile; dashboard chưa có nút xóa draft. Không sửa profile khi đang chạy |
| Đã bấm gửi nhưng trả unknown | Làm đúng phần 13; kiểm tra bài thật/chờ duyệt trước khi cho phép thử lại |
| Thấy skipped_duplicate | Đây là chống trùng; xem chiến dịch trước thay vì liên tục tạo campaign mới |
| Xóa phiên báo lỗi | Đóng mọi thao tác/browser dùng profile rồi thử lại; thông báo lỗi không có nghĩa đã xóa thành công |
| Giao diện thiếu màu/icon hoặc bố cục khác | Kiểm tra việc tải Tailwind/Font Awesome CDN; không suy rằng backend đã ngừng chỉ từ lỗi giao diện |

Khi báo lỗi, gửi tên thao tác, thông báo lỗi, thời điểm, tên khách/cổng và ảnh chụp đã che thông tin nhạy cảm. Không gửi cả thư mục profile, mật khẩu, key hoặc cookie.

## 18. Một buổi dùng thử điển hình

**Chưa có API:** mở VS Code → khởi động khach01 → bật mock → chọn căn mẫu → sửa preview → thêm nhóm → thử login Facebook nếu muốn → chạy pytest. Không mong đợi có bài thật trên nhóm.

**Đã có tích hợp live được xác nhận:** khởi động khach01 → kiểm tra cấu hình/phiên → chọn một căn và một nhóm thử được phép → duyệt nội dung/ảnh → bấm đăng → kiểm tra permalink hoặc hàng chờ trên Facebook → ghi lại kết quả. Chỉ mở rộng sang các nhóm khác sau khi bước thử đạt.

Ví dụ chiến dịch ba nhóm: nhóm A posted, nhóm B pending_approval, nhóm C unknown. Không gửi lại A/B. Kiểm tra nhóm C, xác nhận đúng kết quả; chỉ khi chắc chắn chưa gửi/bị từ chối mới cho phép retry C.

## 19. Các giới hạn cần nhớ

- Bản hiện tại lấy căn qua API, chưa có luồng lấy tin Revoland bằng phiên browser thay API như phương án đã trao đổi.
- Phiên Facebook có thể hết hạn hoặc cần xác minh lại; không cam kết một lần đăng nhập mãi mãi.
- Tự động hóa và việc đăng vào nhóm phải được kiểm tra với quyền tài khoản, quy định nhóm và điều kiện sử dụng áp dụng; không khẳng định đã được Facebook cho phép chỉ vì có phiên khách.
- Không có tự tham gia nhóm, vượt xác minh, tự duyệt bài hoặc nút ép đăng trùng.
- Chưa có lên lịch tương lai, nút hủy campaign, quản lý nhiều tài khoản trên cùng dashboard hoặc import nội dung/ảnh tùy ý thành bài mới độc lập.
- Các nhãn và cấu trúc Facebook có thể thay đổi; thiếu bằng chứng thì tool có thể yêu cầu kiểm tra thủ công.
- Ứng dụng chạy cục bộ. Không mở cổng ra Internet để biến nó thành dịch vụ nhiều người dùng khi chưa bổ sung phân quyền và thiết kế phù hợp.

## 20. Checklist trước khi bàn giao cho khách

- [ ] Máy đã cài được môi trường và mở được dashboard.
- [ ] Tên khách, cổng và thư mục dữ liệu được ghi lại để dùng nhất quán.
- [ ] Nguồn căn live đã được xác nhận endpoint, quyền và trường dữ liệu.
- [ ] Khách đã tự login Facebook, đóng/mở tool và thử dùng lại phiên.
- [ ] Có ít nhất một nhóm mục tiêu được phép thử đăng.
- [ ] Nội dung dài, liên hệ và toàn bộ ảnh được đối chiếu với bài thật.
- [ ] Đã kiểm tra cả nhóm đăng trực tiếp và nhóm chờ duyệt nếu thuộc phạm vi sử dụng.
- [ ] Khách hiểu khác biệt retry, tiếp tục và unknown cần xác minh.
- [ ] Đã thử chống trùng, mất kết nối/gián đoạn và xóa phiên.
- [ ] Đã xác nhận các mục còn lại trong [checklist nghiệm thu](../UAT.md).

## 21. Xuất file Excel cho cả hai loại dữ liệu

### 21.1. Xuất kết quả đăng bài trên giao diện

1. Khởi động tool bằng đúng tên khách.
2. Chọn chiến dịch cần xem trong **Lịch sử**.
3. Bấm **Xuất chiến dịch đang xem**; hoặc bấm **Xuất toàn bộ lịch sử** để lấy mọi chiến dịch của bộ dữ liệu khách hiện tại.
4. Mở danh sách tải xuống của trình duyệt và tìm `ket_qua_dang_bai.xlsx`. Trình duyệt có thể tự thêm số vào tên file nếu đã có bản trước.

Mỗi dòng là một task/nhóm: mã chiến dịch, mã/tiêu đề căn, nguồn dữ liệu live/mock/legacy, trạng thái chiến dịch và nhóm, URL nhóm/bài đăng, lỗi/ghi chú, retry_count, thời gian UTC, bằng chứng và mốc bắt đầu gửi.

File là snapshot tại lúc xuất. Nếu campaign vẫn chạy, báo cáo có thể còn pending/running; cần xuất lại khi hoàn tất. Nếu chưa có lịch sử thì file chỉ có header. Xuất file không chạy đăng bài và không đổi trạng thái task. Nguồn mock/legacy được giữ trong báo cáo, không coi thành công mẫu là đăng thật.

### 21.2. Xuất bình luận hoặc lead JSON trên giao diện

1. Cuộn xuống **Xuất bình luận / lead ra Excel**.
2. Bấm **Tải JSON mẫu**, hoặc dùng file `examples/comments.sample.json` trong project.
3. Chọn file qua **File bình luận JSON**.
4. Bấm **Lọc & xuất Excel**.
5. Mở file `binh_luan_lead.xlsx` trong danh sách tải xuống.

Không cần API Revoland hoặc đăng nhập Facebook cho bước này. Tool đọc file bạn chọn, phân loại bình luận, trích liên hệ và trả Excel. Dữ liệu nhập không được lưu thành hàng chờ lead trên server và không tạo/cập nhật lead trên Revoland.

JSON có thể là mảng trực tiếp, `{"records": [...]}` hoặc `{"comments": [...]}`. Ví dụ bình luận:

```json
[
  {
    "id": "comment_001",
    "author": "Khách mẫu",
    "text": "Cần mua căn này, cuối tuần xem nhà được không?",
    "listing_id": "can_001"
  }
]
```

`text` có thể đổi thành `raw_content`; tên khách nhận `author`, `fb_user_name` hoặc `customer_name`. Có thể bổ sung `source_url` và `created_at`. Mỗi lần tối đa 5 MB, 5.000 bản ghi và 20.000 ký tự cho một bình luận.

Bản ghi lead không có bình luận gốc có thể dùng:

```json
[
  {
    "id": "lead_noi_bo_001",
    "customer_name": "Lead mẫu",
    "phone_number": "0912345678",
    "email": "sample@example.com",
    "listing_id": "can_001",
    "intent_summary": "Khách muốn hẹn xem nhà",
    "sync_status": "not_synced"
  }
]
```

Các ví dụ trên là dữ liệu thử. Lead không có text cần ít nhất điện thoại, email hoặc `revoland_lead_id`; không tự bịa nội dung bình luận. File phân biệt `comment` và `lead`; lead không có bình luận gốc không được chấm điểm ý định từ text.

Excel gồm thông tin gốc, liên hệ, classification, điểm, lý do, signals, mã căn và mã lead nếu có. Chỉ phân loại thì trạng thái là **Lead tiềm năng/Cần xem xét/Bỏ qua**, không ghi đã tạo lead. `sync_status` nhận `not_synced`, `synced`, `failed`, `unconfirmed`; nếu nhập `synced` và mã lead thì file ghi **Đã đồng bộ theo bản ghi**. Đây là thông tin do file cung cấp, không phải kết quả tool vừa xác minh qua API.

### 21.3. Xuất bằng Terminal VS Code

Nếu dashboard dùng khách khach01, mở Terminal thứ hai và đặt đúng thư mục khách:

```powershell
$env:REVOLAND_DATA_DIR = "$env:LOCALAPPDATA\RevolandFBPoster\khach01"

# Toàn bộ lịch sử đăng bài
.\.venv\Scripts\python.exe cli.py --export-posts

# Lọc và xuất file bình luận/lead mẫu
.\.venv\Scripts\python.exe cli.py --export-comments .\examples\comments.sample.json
```

CLI in đường dẫn tuyệt đối của file mới. Mặc định file nằm trong `data/exports` dưới thư mục khách, tên có thời gian và phần ngẫu nhiên để không đè bản cũ. Đừng mở nhầm bộ dữ liệu trong project rồi nghĩ lịch sử khách đã mất.

Chỉ xuất một campaign: thêm `--campaign ID_CHIEN_DICH` vào lệnh `--export-posts`, thay bằng ID thật trong lịch sử. Chọn đường dẫn riêng: thêm `--output .\data\exports\bao_cao_moi.xlsx`. Đuôi phải là `.xlsx`; file đã tồn tại bị từ chối, hãy chọn tên mới. Mỗi lệnh chọn một kiểu export, không dùng hai cờ export cùng lúc.

### 21.4. Nếu chưa thấy file

- Dashboard: kiểm tra mục Downloads của trình duyệt, hộp thoại hỏi chỗ lưu hoặc thông báo ở mục xuất file.
- CLI: đọc dòng **Đã xuất Excel:** và mở đúng đường dẫn đó.
- JSON sai/thiếu dữ liệu: sửa theo mẫu; file Excel sẽ không được tạo cho dữ liệu nhập không hợp lệ.
- File đích đang mở, không ghi được hoặc đã tồn tại: đóng file nếu cần và chọn một đường dẫn/tên mới.
- Có file nhưng chỉ header: kiểm tra đã chọn đúng khách và đã có lịch sử chưa; export không tự tạo dữ liệu nguồn.

## 22. Dùng bản EXE không cần VS Code

Mở `dist/RevolandFBPoster.exe`, chờ giải nén Chromium rồi dashboard tự mở trên trình duyệt. Giữ cửa sổ console trong lúc sử dụng; Ctrl+C để dừng sau khi xử lý xong các task. Không cần cài Python hoặc Playwright trên máy nhận.

Double-click mặc định dùng dữ liệu ở `%LOCALAPPDATA%\RevolandFBPoster\default`. Nếu trước đây dùng khách `khach01`, mở Terminal cạnh EXE rồi chạy:

```powershell
.\RevolandFBPoster.exe --customer khach01
```

Có thể thêm `--port 8001` nếu cổng 8000 đang bận. Dữ liệu đang dùng trực tiếp trong thư mục project không tự chuyển sang thư mục khách của EXE; xem [hướng dẫn EXE](../BUILD_EXE.md) và chọn đúng thư mục/tên khách. File EXE không chứa phiên hoặc cấu hình khách cũ, và không tự xóa dữ liệu cũ.

Tài liệu liên quan: [README](../../README.md) · [Luồng kỹ thuật](PROJECT_FLOW_2026-10.md) · [Từng function](FUNCTION_REFERENCE_2026-10.md) · [Review code](CODE_REVIEW_2026-10-28.md) · [Kiểm thử](VERIFICATION_2026-10.md).
