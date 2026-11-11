# Rà soát và dọn project — 02/11/2026

## Phạm vi

Rà soát entry point, imports Python, API/giao diện, cấu hình, schema, registry/dataset, luồng nhập tin/viết lại/đăng/bình luận/Excel, script cài/chạy/build và tài liệu. Chạy bộ kiểm thử offline trước và sau thay đổi. Không kiểm toán mã thư viện trong `.venv`, đọc nội dung phiên/cookie hoặc gọi Facebook/Revoland/OpenAI thật. Đây là rà soát cấu trúc và chức năng, không phải kiểm toán bảo mật chuyên sâu.

## Đã dọn và sắp xếp

- Xóa 11 thư mục EXE trung gian trong `dist/`, EXE tên cũ `RevolandFBPoster.exe` và hash tương ứng; giữ nguyên EXE chính, SHA256, hướng dẫn và báo cáo xác minh của nó.
- Xóa file build, cache Python và các lần test cũ: lần dọn đầu ghi nhận **3.449 file trong 112 mục, 3.659,34 MiB** (khoảng 3,57 GiB).
- Chuyển dataset QuinLand vào `resources/datasets/quinland.json`, cập nhật loader, self-test và PyInstaller spec. Loader mặc định tìm theo root project/bundle thay vì âm thầm chọn file cùng tên theo thư mục chạy.
- Chuyển 5 JSON từ `New folder` vào `resources/registry_sources/`. Manifest có `source_directory`; test tiếp tục đối chiếu SHA256, không sửa nội dung các JSON gốc.
- Tách 5 module prototype vào `legacy/`, giữ test tại `tests/legacy/`. Các entry point hiện tại không import nhóm module này. Giữ `/posting` và chức năng thử đăng Trang vì chúng vẫn được gọi.
- Gom dữ liệu test/screenshot vào `.cache/`, cập nhật pytest và công cụ kiểm tra EXE để không tiếp tục tạo thư mục ở gốc.
- Loại imports không dùng trong 8 module, rút gọn README, bổ sung hướng dẫn kiến trúc/bảo trì/TXT, chuyển tài liệu cũ sang `docs/archive/` và cập nhật liên kết tương đối.
- Thêm `scripts/clean_project.ps1`: mặc định xem trước, chỉ xóa mục sinh tự động được nhận diện; kiểm tra đường dẫn và symlink/junction; giữ dữ liệu khách, `.venv` và EXE chính.

## Phát hiện chức năng

1. **Test prototype không còn khớp registry hiện tại — đã sửa dữ liệu mẫu.** Trước dọn: 324 đạt, 1 thất bại. Câu “ib mình xin giá và hướng nhà với bạn” có nhiều tín hiệu độc lập nên được phân loại tiềm năng, nhưng test mong cần duyệt. Thay bằng “xin hướng nhà” để kiểm tra đúng nhánh cần duyệt, không đổi quy tắc lọc. Test prototype được buộc dùng client mock.
2. **Tài liệu cách chạy bị mâu thuẫn — đã sửa.** Hướng dẫn cũ nói `run_tool.bat` mở menu; thực tế lệnh mở dashboard, `menu_dev.bat` mới mở menu. README/hướng dẫn hiện tại đã thống nhất, lịch sử cũ được đánh dấu lưu trữ.
3. **Mã nguồn và EXE hiện có khác phiên bản — đã ghi rõ.** Đợt dọn không build hoặc ghi đè EXE. Dùng `run_tool.bat` có `.venv` để nhận tính năng TXT/AI và mã nguồn mới. Muốn phân phối EXE cần build và xác minh lại.
4. **Giới hạn của adapter Revoland cũ vẫn còn.** Preview ở `/posting` dùng URL ảnh ngoài; ảnh đổi nội dung tại cùng URL giữa xem trước và tải có thể khác. `PropertyListing.status` còn mặc định `available`; cần xác nhận trạng thái/quyền đăng theo hợp đồng API thật. Không thay đổi ngầm hợp đồng trong đợt sắp xếp này. Luồng nhập nguồn website/folder hiện tại dùng snapshot/hash riêng.
5. **Prototype đồng bộ lead còn giới hạn, đã cô lập.** Cache client không thực sự cập nhật lead như thông báo và ingest chưa có hàng đợi retry đồng bộ lỗi. Những module này nằm trong `legacy/`, không phải luồng lọc lead trên dashboard. Chi tiết gốc trong [review lưu trữ](archive/CODE_REVIEW_2026-10-28.md).
6. **Còn một cảnh báo tương thích của test framework.** Starlette cảnh báo đường tích hợp TestClient/httpx hiện tại. Không nâng cấp dependency trong đợt dọn; cần xử lý riêng khi cập nhật lock và chạy lại toàn bộ test.

## Xác minh

- Kiểm tra cú pháp/import trên **51 module Python**, 4 script PowerShell và PyInstaller spec; 11 JSON nguồn/dataset/registry hợp lệ. Không còn imports thừa qua kiểm tra AST trên các module ứng dụng/prototype.
- Kiểm tra liên kết tài liệu nội bộ và SHA256 nguồn registry sau khi chuyển.
- Bộ test liên quan sau sắp xếp ban đầu: **64 đạt**.
- Bộ kiểm thử đầy đủ sau dọn: **328 đạt, 1 cảnh báo**, trong 210,90 giây. Bao gồm browser test offline và kiểm tra script dọn trên project giả lập (xem trước, giữ dữ liệu, chặn release có file lạ và chặn symlink/junction).
- Kiểm tra lại lần cuối phần script dọn và menu: **12 đạt**. File tạm của các lần xác minh được dọn sau khi ghi báo cáo.
- Self-test của launcher mã nguồn: **đạt**, gồm asset giao diện, dataset QuinLand, registry/ngữ cảnh/phủ định, SQLite, Excel và Chromium với runtime cô lập.
- SHA256 của EXE chính vẫn khớp manifest phát hành ban đầu; không build lại hay khẳng định EXE đã chứa thay đổi mới.

Không nghiệm thu đăng Facebook, API Revoland hoặc chất lượng paraphrase qua API thật trong đợt này. [Checklist nghiệm thu](UAT.md) dành cho môi trường có tài khoản và quyền phù hợp.
