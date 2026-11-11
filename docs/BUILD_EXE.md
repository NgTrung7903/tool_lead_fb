# Chạy và build EXE Windows

Bản mới nhất là `dist/revoland-link-v18/CongCuBDS_JSON.exe` (2026.11.11-link.18). Bước 2 ưu tiên dán link Revoland hoặc link JSON để lấy dữ liệu, soạn nội dung và tải ảnh. Trong tab **Khách hàng**, cột **Nhóm** nằm cạnh các bình luận tương ứng. Mỗi khách vẫn có một dòng, với từng nhóm được tách riêng trong dòng đó. Đóng bản cũ trước khi mở EXE mới.

## Dùng bản đã đóng gói

Nhấp đúp **CongCuBDS_JSON.exe** để mở giao diện tại http://127.0.0.1:8000. Xem [hướng dẫn Facebook](FACEBOOK_WORKFLOW.md). Giữ console mở khi dùng công cụ. Chờ tác vụ đăng kết thúc và dừng lấy bình luận nếu đang chạy trước khi bấm Ctrl+C để đóng.

EXE chứa Python runtime, code, giao diện, registry, thư viện Excel và Chromium. Máy nhận không cần Python/VS Code/Playwright riêng. Internet cần cho Facebook; giao diện lọc lead dùng CSS/JS cục bộ. Tool hỗ trợ lấy bình luận bằng phiên Facebook và nhập JSON/dán nội dung. Chưa nghiệm thu với Facebook thật; không cam kết lấy đủ bình luận. Công cụ đăng bài cũ ở `/posting` vẫn cần API Revoland phù hợp.

Dữ liệu mặc định nằm ở `%LOCALAPPDATA%\RevolandFBPoster\default`, không nằm trong file EXE hoặc thư mục giải nén tạm. API key, cookie, profile và lịch sử trên máy build không được đưa vào gói.

Nếu trước đây chạy `start.ps1 -Customer khach01`, mở PowerShell ở thư mục EXE và chạy:

```powershell
.\CongCuBDS_JSON.exe --customer khach01
```

Nếu cổng đang bận:

```powershell
.\CongCuBDS_JSON.exe --customer khach01 --port 8001
```

`REVOLAND_DATA_DIR` được đặt rõ trong môi trường sẽ được ưu tiên; không đổi biến này nếu muốn tiếp tục dữ liệu theo tên khách. Chỉ chạy một dashboard cho mỗi bộ dữ liệu. Khi báo đang có bản khác chạy, mở lại cửa sổ hiện có hoặc đóng bản cũ.

Bản phát hành là console EXE, chưa ký số và chưa có bộ cài/auto-update. Không cần quyền Administrator để dùng bình thường. Việc xác minh kỹ thuật trên máy build không thay thế thử trên máy khách sạch hoặc nghiệm thu tài khoản Facebook thật.

## Tái tạo bản build

Cài môi trường ứng dụng và Chromium theo README rồi chạy:

```powershell
.\build_exe.ps1
```

Script cài `requirements-build.txt`, xác định revision Chromium của Playwright đang cài và gọi spec. Spec chỉ gom các tài nguyên được chỉ định: `api/static`, `core/registry`, `examples`, `resources/datasets` và một revision Chromium; không gom cả thư mục project.

`desktop_launcher.py` đặt thư mục dữ liệu trước khi import service. Trong bản frozen, `PLAYWRIGHT_BROWSERS_PATH` trỏ vào browser đi kèm; `launch_context()` chỉ định executable Chromium đầy đủ cho cả headless và có cửa sổ, tránh phụ thuộc headless shell trong cache máy build.

Phương thức dùng Playwright với PyInstaller được mô tả trong [tài liệu Playwright](https://playwright.dev/python/docs/library#pyinstaller). Cách tách dữ liệu bền vững khỏi thư mục giải nén của one-file theo [tài liệu runtime PyInstaller](https://pyinstaller.org/en/stable/runtime-information.html).

## Xác minh bản EXE

```powershell
.\.venv\Scripts\python.exe packaging\verify_exe.py
```

Script tạo runtime kiểm thử riêng, bỏ PYTHONHOME/PYTHONPATH/VIRTUAL_ENV và dùng PATH hệ thống tối thiểu. Cố ý đặt cache browser ngoài gói thành đường dẫn không tồn tại, rồi kiểm:

- HTML, JavaScript và registry nằm trong gói.
- SQLite và xuất Excel hoạt động.
- Chromium đi kèm khởi động được với trang offline.
- Chính EXE mở server, trả dashboard mới, 5 registry, lọc dữ liệu mẫu và xuất XLSX qua HTTP; kiểm cả API cũ.
- Dữ liệu cấu hình trả về không lộ key.

Không dùng tài khoản hay API thật. Server kiểm thử được đóng cùng các tiến trình con sau khi hoàn tất. Kết quả ở `dist/EXE_VERIFICATION.json`; log ở `.cache/test-runs/exe-verification-*`.

## Kiểm tra tải ảnh HTTPS trong EXE

Bản Python đi kèm runtime có file chính sách SSL `codex-rejected-cas.pem` cạnh `ssl.py`. Spec gom file này vào thư mục gốc của gói khi runtime có sử dụng nó. Thiếu file sẽ gây `ConnectionError` với nguyên nhân `FileNotFoundError` khi tạo SSLContext, dù JSON vẫn nạp và Chromium vẫn chạy. Giữ nguyên xác minh chứng chỉ HTTPS.

Self-test tạo SSLContext để bắt lỗi thiếu dữ liệu SSL ngay cả khi chạy offline. Có thể xác minh thêm ảnh thật bằng:

```powershell
.\.venv\Scripts\python.exe packaging\verify_image_download.py dist\image-fix-v7\CongCuBDS_JSON.exe 'C:\Users\nt583\Downloads\QuinLand.Properties (2).json'
```

Lệnh dùng runtime thử riêng, lấy các tin đầu/giữa/cuối, kiểm tra từng ảnh qua endpoint xem trước của EXE rồi đóng server thử. Báo cáo `IMAGE_DOWNLOAD_VERIFICATION.json` nằm cạnh EXE.



