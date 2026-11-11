# Kiến trúc project

Cập nhật 02/11/2026. Ứng dụng Python/FastAPI chạy cục bộ trên Windows, giao diện HTML/JavaScript và tự động hóa trình duyệt bằng Playwright.

## Các thư mục

| Vị trí | Nội dung |
| --- | --- |
| `api/` | FastAPI và giao diện trong `static/` |
| `services/` | Nghiệp vụ đang dùng: nhập nguồn, đăng nhóm, phiên, bình luận, Excel |
| `core/` | Trích xuất liên hệ, bộ lọc và 5 registry hoạt động |
| `models/` | Schema dữ liệu; còn một số kiểu tương thích prototype |
| `config/settings.py` | Cấu hình mặc định và đường dẫn dữ liệu khách |
| `resources/datasets/` | Dataset QuinLand tích hợp, được đóng gói vào EXE |
| `resources/registry_sources/` | 5 JSON đầu vào gốc, giữ SHA256 để đối chiếu; không thay thế registry đang chạy |
| `tests/` | Kiểm thử hiện tại; `tests/legacy/` kiểm thử prototype |
| `legacy/` | Prototype cũ, không import từ các entry point hiện tại |
| `packaging/` | Spec PyInstaller, kiểm tra EXE và hướng dẫn bản đóng gói |
| `scripts/` | Công cụ bảo trì project |
| `docs/` | Hướng dẫn hiện tại; `archive/` lưu tài liệu lịch sử |
| `.cache/` | File test, screenshot và cache có thể tạo lại |
| `build/`, `dist/` | Kết quả đóng gói, không phải mã nguồn |

## Entry point và luồng dữ liệu

- `run_tool.bat` ưu tiên Python trong `.venv`, gọi `desktop_launcher.py`; chỉ dùng EXE nếu không có Python trong project. Launcher chọn runtime khách trước khi import service, mở dashboard và xử lý cổng bận.
- `start.ps1` chạy server với khách/cổng được chỉ định. `menu_dev.bat` / `menu.py` cung cấp menu kỹ thuật. `cli.py` chứa các thao tác nâng cao.
- `/` dùng `workflow.html`, `workflow.js` và `common.js`. Nguồn JSON/website/QuinLand đi qua `WebsiteSourceService`, lưu SQLite và ảnh snapshot.
- `CampaignService` lưu nội dung/ảnh đã duyệt và kết quả bền vững trong SQLite; `GroupManager` lưu nhóm; `FacebookPosterEngine` thao tác đăng và xác minh. Nội dung chỉ gửi khi người dùng chủ động bắt đầu đợt đăng.
- `FacebookSessionManager` và `facebook_browser.py` quản lý profile/khóa. `FacebookCommentCollector` lấy bình luận, `LeadFilterService` lưu lịch sử và ngữ cảnh. `RegistryFilterEngine` phân loại cục bộ, không dùng AI.
- `/leads` dùng `leads.html`, `leads.js`, `common.js`; báo cáo qua `report_service.py` và `excel_exporter.py`.
- `/posting` với `index.html` / `app.js` là giao diện Revoland cũ **vẫn truy cập được**, nên được giữ lại. Khác với các prototype không nối runtime trong `legacy/`.
- `page_post_service.py` vẫn được CLI gọi để thử đăng Trang; không xóa vì chưa nằm trên dashboard.

## Dữ liệu khách và tài nguyên đóng gói

Launcher mặc định lưu dữ liệu ở `%LOCALAPPDATA%/RevolandFBPoster/<customer>`. `REVOLAND_DATA_DIR` ghi đè khi được đặt rõ. Chạy một số module trực tiếp mà không qua launcher có thể dùng thư mục project để tương thích bản cũ.

`data/`, `profiles/`, `browser_data/` và `config/config.json`, `config/groups.json` đang có trong project có thể là dữ liệu thật. Script dọn không đụng vào các vị trí này hoặc `.venv`. Không di chuyển chúng khi ứng dụng đang chạy.

PyInstaller chỉ gom asset giao diện, registry đang dùng, ví dụ, dataset QuinLand và Chromium; không gom nguồn registry tham khảo, tài liệu lịch sử, prototype hay dữ liệu khách. Dataset được tìm theo `ROOT_DIR/resources/datasets/quinland.json`, độc lập thư mục chạy hiện tại.

## Kiểm thử và bảo trì

`tests/conftest.py` tạo runtime cô lập trong `.cache/test-runs/` và chặn HTTP ngoài. Pytest dùng `.cache/pytest/` cho file tạm, `.cache/pytest-cache/` cho cache. Browser test intercept trang/API, không đăng bài thật.

Xem [README](../README.md), [cách dọn project](MAINTENANCE.md) và [kết quả rà soát](PROJECT_REVIEW.md).
