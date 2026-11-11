"""Kiểm thử toàn diện luồng nghiệp vụ End-to-End (Tin -> Nhóm -> Bình luận -> Lọc -> Tạo Lead / Duyệt).
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from models.schema import Listing
from legacy.comment_pipeline import CommentPipeline
from legacy.facebook_service import FacebookService
from legacy.revoland_client import RevolandClient


def test_full_pipeline_flow():
    print("\n=======================================================")
    print("CHẠY KIỂM THỬ TOÀN LUỒNG END-TO-END (MVP REVOLAND TOOL)")
    print("=======================================================")

    # 1. Khởi tạo dịch vụ
    fb_service = FacebookService()
    pipeline = CommentPipeline(revoland_client=RevolandClient(mock_mode=True))

    # 2. Tạo tin đăng mẫu
    sample_listing = Listing(
        id="list_101",
        revoland_listing_id="REV_LISTING_99",
        title="Bán căn hộ 2PN 70m2 Vinhomes Grand Park, tầng cao view đẹp",
        content="Căn hộ 2PN 2WC full nội thất cao cấp. Pháp lý chuẩn chỉnh có sổ, hỗ trợ vay 70%.",
        price_text="2.8 Tỷ",
        location_text="TP. Thủ Đức, TP.HCM",
        media_urls=["https://revoland.vn/photos/can1.jpg"]
    )
    print(f"\n1. Đã chuẩn bị tin đăng: '{sample_listing.title}' ({sample_listing.price_text})")

    # 3. Chọn nhóm Facebook và tạo tác vụ phân phối
    groups = fb_service.list_groups()
    selected_group_ids = [groups[0].id, groups[1].id]
    tasks = fb_service.create_distribution_campaign(sample_listing, selected_group_ids)
    print(f"2. Đã tạo {len(tasks)} tác vụ đăng tin lên nhóm Facebook.")

    # Mô phỏng hỗ trợ đăng tay: Lấy payload copy
    assisted_payload = fb_service.get_assisted_post_payload(tasks[0].id, sample_listing)
    print(f"   -> Link nhóm để đăng: {assisted_payload['group_url']}")
    print(f"   -> Đã format nội dung để copy:")
    for line in assisted_payload['formatted_text'].splitlines()[:3]:
        print(f"      | {line}")

    # Đánh dấu tác vụ đã đăng
    fb_service.mark_task_posted(tasks[0].id, post_url="https://facebook.com/groups/bds.thuduc/posts/111222333")
    print(f"   -> Tác vụ đã đăng xong. URL bài viết: {tasks[0].post_url}")

    # 4. Tiếp nhận bình luận
    print("\n3. Tiếp nhận 4 bình luận thực tế:")

    # Comment A: Lead tiềm năng rõ nét
    res_a = pipeline.ingest_comment(
        raw_content="Cần mua căn này, cuối tuần xem được không? SĐT 0912345678",
        fb_user_name="Nguyễn Văn Minh",
        fb_user_id="fb_user_minh_01",
        listing_id=sample_listing.id,
        posting_task_id=tasks[0].id
    )
    print(f"   [Bình luận 1] 'Cần mua căn này, cuối tuần xem được không? SĐT 0912345678'")
    print(f"      => Kết quả lọc: {res_a['classification']} | Hành động: {res_a['pipeline_action']}")
    assert res_a["classification"] == "LEAD_POTENTIAL"
    assert res_a["pipeline_action"] == "auto_lead_created"

    # Comment B: Chỉ hỏi hướng nhà, chưa có thêm tín hiệu độc lập.
    res_b = pipeline.ingest_comment(
        raw_content="xin hướng nhà",
        fb_user_name="Trần Thị Lan",
        fb_user_id="fb_user_lan_02",
        listing_id=sample_listing.id,
        posting_task_id=tasks[0].id
    )
    print(f"   [Bình luận 2] 'xin hướng nhà'")
    print(f"      => Kết quả lọc: {res_b['classification']} | Hành động: {res_b['pipeline_action']}")
    assert res_b["classification"] == "NEEDS_REVIEW"
    assert res_b["pipeline_action"] == "queued_for_review"

    # Comment C: Bỏ qua (Spam vay vốn)
    res_c = pipeline.ingest_comment(
        raw_content="Vay vốn ngân hàng giải ngân 24h lãi suất thấp không thế chấp alo 0988999111",
        fb_user_name="Tài Chính Nhanh",
        fb_user_id="fb_user_spam_03",
        listing_id=sample_listing.id,
        posting_task_id=tasks[0].id
    )
    print(f"   [Bình luận 3] 'Vay vốn ngân hàng giải ngân 24h...'")
    print(f"      => Kết quả lọc: {res_c['classification']} | Hành động: {res_c['pipeline_action']}")
    assert res_c["classification"] == "IGNORE"

    # Comment D: Gửi lại bình luận trùng lặp (Anti-duplication check)
    res_d = pipeline.ingest_comment(
        raw_content="Cần mua căn này, cuối tuần xem được không? SĐT 0912345678",
        fb_user_name="Nguyễn Văn Minh",
        fb_user_id="fb_user_minh_01",
        listing_id=sample_listing.id,
        posting_task_id=tasks[0].id
    )
    print(f"   [Bình luận 4 (Trùng lặp)] Gửi lại bình luận 1")
    print(f"      => Kết quả chống trùng: {res_d['action']} - {res_d['message']}")
    assert res_d["action"] == "duplicate_skipped"

    # 5. Xử lý Hàng chờ duyệt (Review Queue)
    review_queue = pipeline.list_review_queue()
    print(f"\n4. Kiểm tra Hàng chờ duyệt: Có {len(review_queue)} mục cần sale xử lý.")
    assert len(review_queue) == 1
    target_review = review_queue[0]
    print(f"   -> Bình luận chờ duyệt: '{target_review['comment_text']}' của {target_review['customer_name']}")

    # Sale bấm DUYỆT mục này
    approve_res = pipeline.approve_review_item(
        review_id=target_review["review_id"],
        reviewer_id="sale_leader_tu",
        phone_override="0988777666",
        note_override="Đã gọi điện tư vấn, khách thiện chí muốn xem vào Chủ Nhật"
    )
    print(f"   -> Sale đã bấm DUYỆT: {approve_res['message']}")
    print(f"      Mã Lead Revoland mới: {approve_res['lead']['revoland_lead_id']}")

    # 6. Kiểm tra danh sách Lead cuối cùng
    all_leads = pipeline.list_leads()
    print(f"\n5. Tổng số Lead đã tạo trên Revoland: {len(all_leads)} Lead")
    for idx, lead in enumerate(all_leads, 1):
        print(f"   Lead {idx}: {lead['customer_name']} | SĐT: {lead['phone_number']} | Revoland ID: {lead['revoland_lead_id']}")
    assert len(all_leads) == 2

    print("\n✓ TOÀN BỘ KIỂM THỬ END-TO-END ĐÃ ĐẠT 100% TIÊU CHUẨN!")


if __name__ == "__main__":
    test_full_pipeline_flow()
