# Prototype cũ

Các module ở đây thuộc prototype ban đầu, không được dashboard `/`, `/leads`, `/posting` hoặc CLI hiện tại import. Giữ để tham khảo và chạy kiểm thử tương thích tại `tests/legacy/`.

| Module | Vai trò cũ |
| --- | --- |
| `browser_manager.py` | Crawl tổng quát với profile trong `browser_data/` |
| `facebook_service.py` | Đăng hỗ trợ thủ công, dữ liệu nhóm/tác vụ trong RAM |
| `comment_pipeline.py` | Tự đồng bộ lead Revoland từ bình luận |
| `revoland_client.py` | Client tạo lead, cache trong RAM |
| `dedup.py` | Khóa chống trùng của prototype |

Luồng hiện tại dùng `services/facebook_browser.py`, `campaign_service.py`, `lead_filter_service.py` và `group_manager.py`. Không nối lại prototype vào ứng dụng trước khi thống nhất lưu trữ, khóa profile, chống trùng và hợp đồng API. Client cũ vẫn có giới hạn đã ghi nhận: nhánh cache không thực sự cập nhật lead và đồng bộ lỗi chưa có hàng đợi retry. Xem [báo cáo project](../docs/PROJECT_REVIEW.md).
