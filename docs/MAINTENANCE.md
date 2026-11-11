# Bảo trì và dọn project

Chạy PowerShell tại thư mục project. Dừng kiểm thử/build trước khi dọn.

## Dọn file sinh tự động

Xem danh sách và dung lượng trước khi xóa:

```powershell
.\scripts\clean_project.ps1
```

Xóa các mục đã liệt kê:

```powershell
.\scripts\clean_project.ps1 -Apply
```

Script chọn cache Python trong các thư mục mã nguồn được chỉ định, toàn bộ `.cache/`, `build/` và các thư mục `.pytest-*`, `.pytest_cache`, `.test-runs` cũ. Thư mục `.cache/` chứa kết quả kiểm thử, ảnh thử và file build có thể tạo lại. Trước khi dọn, sao chép báo cáo cần giữ sang thư mục bàn giao. Script kiểm tra đường dẫn nằm trong project và từ chối symlink/junction trước khi xóa. Có thể dùng `-WhatIf` để thử chế độ xóa.

`-OldReleases` bổ sung các thư mục bản build trung gian đã liệt kê trong script, gồm v10 đến v17. Nội dung không nhận diện trong thư mục release khiến script dừng trước khi xóa. Bản hiện tại nằm tại `dist/revoland-link-v18/`.

Không dùng script này để dọn `data/`, `profiles/`, `browser_data/`, cấu hình khách, `resources/`, `.venv` hay `%LOCALAPPDATA%`. Muốn xóa dữ liệu khách cần xác định đúng khách và sao lưu riêng.

## Giữ project gọn khi kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -m "not browser" -q
```

Không truyền `--basetemp=.pytest-ten-moi` mỗi lần chạy; cấu hình mặc định đã gom file tạm vào `.cache`. Tránh chạy đồng thời hai bộ pytest dùng chung basetemp. Log/screenshot kiểm tra EXE cũng ở `.cache/test-runs/`.

## Bản EXE và dependency

Mã nguồn thay đổi không tự cập nhật EXE. Chạy `run_tool.bat` trong project có `.venv` để dùng mã mới. Khi cần giao bản mới, làm theo [BUILD_EXE.md](BUILD_EXE.md), chạy xác minh rồi phân phối một bản chính trong `dist/`.

Giữ `requirements.txt` (dependency trực tiếp), `requirements-lock.txt` (phiên bản cố định), `requirements-dev.txt` (test) và `requirements-build.txt` (đóng gói). Không gộp/xóa các file này chỉ vì tên gần giống; chúng có vai trò khác nhau. Đợt dọn này không nâng cấp dependency hoặc cài thêm gói.


