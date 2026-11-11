# Tài nguyên dùng chung

- `datasets/quinland.json`: kho tin tùy chọn chứa dữ liệu thực, được cấp riêng và loại khỏi Git. Xem [cách bổ sung dataset](datasets/README.md).
- `registry_sources/`: 5 JSON gốc dùng để xây dựng registry, giữ nguyên tên và nội dung để đối chiếu SHA256 trong `docs/REGISTRY_IMPORT_SOURCES.json`.

Registry đang chạy nằm tại `core/registry/`. Không sửa nguồn tham khảo để thay đổi kết quả lọc; cần sửa registry hoạt động và chạy kiểm thử.
