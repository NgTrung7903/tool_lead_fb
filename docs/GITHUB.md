# Đưa mã nguồn lên GitHub

Repository chỉ chứa mã nguồn, tài liệu, dữ liệu mẫu và tài nguyên dùng chung. `.gitignore` loại trừ môi trường Python, cache, bản build, `output/`, dữ liệu khách, profile trình duyệt, cấu hình riêng, cơ sở dữ liệu và khóa truy cập. Các file này vẫn được giữ trên máy.

Các thư mục `Data_tool/`, `Tool/` và `toolfb/` là repository riêng được clone trong workspace, được loại khỏi repository gốc. Khi cần cập nhật một repository đó, chạy Git trong đúng thư mục của nó.

Dataset `resources/datasets/quinland.json` chứa dữ liệu bất động sản và thông tin liên hệ thật, được phân phối riêng. Xem [hướng dẫn dataset](../resources/datasets/README.md). Sau khi clone, luồng nạp link và JSON dùng được, còn kho QuinLand cần bổ sung dataset nội bộ nếu sử dụng. Các bài kiểm thử và xác minh bản đóng gói có yêu cầu kho 250 tin cũng cần dataset này.

## Kiểm tra trước khi commit

Chạy tại thư mục project:

```powershell
git status --short
git add .
git diff --cached --stat
git diff --cached
```

Kiểm tra nội dung sắp commit không có token, mật khẩu, cookie hoặc dữ liệu khách. Không dùng `git add -f` cho file đã bị loại trừ. `.gitignore` không tự gỡ file đã được theo dõi trong các commit trước đó.

## Commit và push lần đầu

Tạo một repository trống trên GitHub, thay URL mẫu bằng URL repository của bạn:

```powershell
git commit -m "Initial source import"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

Không lưu token GitHub trong URL remote hoặc file mã nguồn. File EXE có thể phân phối qua GitHub Releases thay vì commit vào repository.

Repository gốc của workspace hiện chưa có commit hoặc remote. Thay URL mẫu bằng repository đích trước khi push. Kiểm tra `git remote -v` tại thư mục gốc để xác nhận đúng repository.

## Chạy sau khi clone

```powershell
.\install.ps1
.\start.ps1 -Customer khach01 -Port 8000
```

Cấu hình cục bộ được ứng dụng tạo khi cần. Nhập khóa API thật trên máy sử dụng; không đưa khóa vào cấu hình mặc định trong mã nguồn.
