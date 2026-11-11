# Công cụ BĐS Facebook

Ứng dụng Windows để nạp link Revoland hoặc dữ liệu JSON, soạn nội dung từ thông tin tin đăng, duyệt và đăng nhóm Facebook, lấy bình luận, lọc khách tiềm năng và xuất Excel.

## Mở tool

Xem [hướng dẫn chạy và sử dụng](docs/USER_GUIDE.md). Bản PDF/HTML có ảnh, nếu đã tạo trên máy, nằm trong `output/pdf/` và không đưa vào Git.

Bản EXE bàn giao cục bộ nằm tại `dist/revoland-link-v18/CongCuBDS_JSON.exe` (2026.11.11-link.18). EXE được phân phối riêng qua bộ bàn giao hoặc GitHub Releases. Xem [biên bản rà soát và bàn giao](docs/HANDOVER_REVIEW.md) và [hướng dẫn đóng gói](docs/BUILD_EXE.md). Bảng Khách hàng có cột Nhóm cạnh bình luận, gom mỗi người một dòng.

Gói gửi công ty nằm tại `dist/Ban_giao_CongCuBDS_Facebook_v18.zip`, gồm EXE, hướng dẫn có hình, JSON mẫu, báo cáo kiểm thử và checklist nghiệm thu.

Nhấp đúp **`run_tool.bat`**. Khi có `.venv`, lệnh này chạy mã nguồn hiện tại và tự mở trình duyệt. Giữ cửa sổ console trong lúc dùng; chờ tác vụ kết thúc trước khi đóng.

Nếu cần menu kỹ thuật, chạy **`menu_dev.bat`**. Đóng cửa sổ tool cũ trước khi mở EXE mới. Khi mã nguồn thay đổi, cần build lại để cập nhật EXE.

Cài môi trường lần đầu hoặc chạy khách riêng:

```powershell
.\install.ps1
.\start.ps1 -Customer khach01 -Port 8000
```

Dữ liệu của launcher mặc định nằm tại `%LOCALAPPDATA%/RevolandFBPoster/<customer>`. `REVOLAND_DATA_DIR` được ưu tiên nếu đã đặt. Chỉ chạy một tiến trình trên một bộ dữ liệu khách.

## Luồng sử dụng

1. Dán link chi tiết Revoland rồi bấm **Lấy tin & soạn nội dung**. Công cụ đọc dữ liệu JSON của đúng mã tin, tạo nội dung từ tiêu đề, giá, vị trí, diện tích và mô tả, rồi tải ảnh để duyệt. Cũng có thể nạp link JSON/API hoặc chọn file JSON tại mục bên dưới. Xem [cấu trúc JSON](docs/JSON_POSTS.md).
2. Tìm bài theo tiêu đề hoặc chuyển trang (100 bài/trang). Kiểm tra nội dung và ảnh; sửa trực tiếp nội dung nếu cần. Có thể xóa bài đang chọn, chọn nhiều bài để xóa hoặc xóa toàn bộ kho trên máy; không xóa bài trên Facebook hay các đợt đăng đã lưu.
3. Đăng nhập Facebook, chọn nhóm, đánh dấu đã duyệt và lưu đợt đăng. Bấm **Bắt đầu đăng** để gửi thật.
4. Theo dõi kết quả và link bài; chủ động lấy bình luận, xem phân loại/lý do và tải Excel.

Các trang `/`, `/leads`, `/posting` dùng chung server. `/posting` là giao diện Revoland cũ vẫn được hỗ trợ. Threads/Zalo chưa triển khai. Kiểm thử offline không thay thế nghiệm thu Facebook/API thật.

## Cấu trúc

| Thư mục | Mục đích |
| --- | --- |
| `api/`, `services/`, `core/`, `models/`, `config/` | Mã ứng dụng và registry đang dùng |
| `resources/` | Dataset QuinLand và nguồn registry gốc có SHA256 |
| `tests/` | Kiểm thử; prototype được kiểm tra tại `tests/legacy/` |
| `legacy/` | Prototype tham khảo, không nối dashboard/CLI hiện tại |
| `docs/` | Hướng dẫn và báo cáo; tài liệu cũ nằm trong `docs/archive/` |
| `scripts/`, `packaging/` | Bảo trì và đóng gói |
| `.cache/` | Dữ liệu test, screenshot, cache sinh tự động |
| `.venv/`, `build/`, `dist/` | Môi trường Python, file build và bản phân phối |

Giữ nguyên `data/`, `profiles/`, `browser_data/`, cấu hình khách nếu đang dùng chế độ lưu dữ liệu cũ trong project. Không coi chúng là file rác.

## Kiểm thử và dọn dẹp

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\clean_project.ps1
.\scripts\clean_project.ps1 -Apply
```

Lệnh dọn mặc định chỉ xem trước; `-Apply` xóa cache/test/build được nhận diện, giữ dữ liệu khách và EXE chính. Không chạy dọn cùng lúc với test/build. Xem [bảo trì](docs/MAINTENANCE.md).

## Tài liệu

Dataset QuinLand chứa dữ liệu thực được cấp riêng và loại khỏi Git. Sau khi clone, xem [cách bổ sung dataset](resources/datasets/README.md) nếu cần kho QuinLand hoặc chạy bộ kiểm tra gói đầy đủ.

- [Chuẩn bị và đẩy mã nguồn lên GitHub](docs/GITHUB.md)
- [Hướng dẫn chạy và sử dụng](docs/USER_GUIDE.md)
- [Luồng nhập tin → đăng → lọc lead](docs/FACEBOOK_WORKFLOW.md)
- [Bộ lọc khách hàng](docs/LEAD_FILTER.md) và [registry](docs/REGISTRIES.md)
- [Kiến trúc và dữ liệu](docs/ARCHITECTURE.md)
- [Đóng gói và xác minh EXE](docs/BUILD_EXE.md)
- [Rà soát và dọn project ngày 02/11/2026](docs/PROJECT_REVIEW.md)
- [Checklist nghiệm thu thực tế](docs/UAT.md)


