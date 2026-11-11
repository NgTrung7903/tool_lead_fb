"""Luồng tiếp nhận, lọc và phân loại bình luận đầu cuối (End-to-End Comment Pipeline).
Kết nối:
Bình luận FB -> Chống trùng -> Bộ lọc Registry Engine -> (Tự tạo Lead Revoland | Hàng chờ duyệt | Bỏ qua)
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from legacy.dedup import generate_comment_hash
from core.filter_engine import RegistryFilterEngine
from models.schema import (
    ClassificationEnum,
    FBComment,
    ReviewItem,
    ReviewStatusEnum,
    RevolandLead,
    utc_now_iso
)
from legacy.revoland_client import RevolandClient


class CommentPipeline:
    def __init__(self, filter_engine: Optional[RegistryFilterEngine] = None, revoland_client: Optional[RevolandClient] = None):
        self.filter_engine = filter_engine or RegistryFilterEngine()
        self.revoland_client = revoland_client or RevolandClient()

        # Database trong bộ nhớ cho MVP (có thể map sang SQLite / MongoDB)
        self.comments_db: Dict[str, FBComment] = {}
        self.review_queue_db: Dict[str, ReviewItem] = {}
        self.leads_db: Dict[str, RevolandLead] = {}
        self._processed_hashes: set[str] = set()

    def ingest_comment(
        self,
        raw_content: str,
        fb_user_name: str = "Khách Facebook",
        fb_user_id: Optional[str] = None,
        fb_comment_id: Optional[str] = None,
        listing_id: Optional[str] = None,
        posting_task_id: Optional[str] = None,
        source_type: str = "manual_paste"
    ) -> Dict[str, Any]:
        """Tiếp nhận 1 bình luận, lọc qua registry và điều hướng kết quả."""
        cid = fb_comment_id or f"cmt_{uuid.uuid4().hex[:8]}"
        user_id = fb_user_id or f"usr_{uuid.uuid4().hex[:6]}"

        # 1. Chống trùng lặp nội dung từ cùng người dùng
        comment_hash = generate_comment_hash(listing_id or "default", user_id, raw_content)
        if comment_hash in self._processed_hashes:
            return {
                "success": False,
                "action": "duplicate_skipped",
                "message": "Bình luận này đã được tiếp nhận và xử lý trước đó (Trùng mã băm).",
                "comment_id": cid
            }
        self._processed_hashes.add(comment_hash)

        # 2. Đánh giá qua Registry Filter Engine (Không LLM)
        eval_result = self.filter_engine.evaluate(raw_content)
        classification = ClassificationEnum(eval_result["classification"])

        comment_obj = FBComment(
            id=cid,
            listing_id=listing_id,
            posting_task_id=posting_task_id,
            fb_comment_id=fb_comment_id,
            fb_user_id=user_id,
            fb_user_name=fb_user_name,
            raw_content=raw_content,
            source_type=source_type,
            classification=classification,
            score=eval_result["score"],
            reasons=eval_result["reasons"],
            signals=eval_result["signals"]
        )
        self.comments_db[cid] = comment_obj

        # 3. Điều hướng xử lý theo 3 kết quả nghiệp vụ
        pipeline_action = ""
        lead_result = None

        if classification == ClassificationEnum.LEAD_POTENTIAL:
            # TỰ TẠO HOẶC CẬP NHẬT LEAD REVOLAND
            contacts = eval_result["contacts"]
            primary_phone = contacts.get("primary_phone")
            primary_email = contacts["emails"][0] if contacts.get("emails") else None

            lead_sync = self.revoland_client.create_or_update_lead(
                listing_id=listing_id or "LISTING_GENERAL",
                customer_name=fb_user_name,
                phone_number=primary_phone,
                email=primary_email,
                fb_user_id=user_id,
                fb_comment_id=cid,
                note=f"[Auto-Lead Registry] Điểm: {comment_obj.score:.0f}. {'; '.join(comment_obj.reasons[:2])}"
            )

            lead_id = f"lead_{uuid.uuid4().hex[:8]}"
            lead_obj = RevolandLead(
                id=lead_id,
                revoland_lead_id=lead_sync.get("revoland_lead_id"),
                comment_id=cid,
                listing_id=listing_id,
                customer_name=fb_user_name,
                phone_number=primary_phone,
                email=primary_email,
                intent_summary="; ".join(eval_result["reasons"][:3]),
                sync_status="synced" if lead_sync.get("success") else "failed",
                revoland_response=lead_sync
            )
            self.leads_db[lead_id] = lead_obj
            pipeline_action = "auto_lead_created" if lead_sync.get('success') else 'lead_sync_failed'
            lead_result = lead_obj.model_dump()

        elif classification == ClassificationEnum.NEEDS_REVIEW:
            # CHUYỂN HÀNG CHỜ NHÂN VIÊN DUYỆT
            review_id = f"rev_{uuid.uuid4().hex[:8]}"
            review_obj = ReviewItem(
                id=review_id,
                comment_id=cid,
                status=ReviewStatusEnum.PENDING
            )
            self.review_queue_db[review_id] = review_obj
            pipeline_action = "queued_for_review"

        else:
            # BỎ QUA VÀ GHI LOG
            pipeline_action = "ignored_and_logged"

        return {
            "success": not (pipeline_action == 'lead_sync_failed'),
            "comment_id": cid,
            "classification": classification.value,
            "pipeline_action": pipeline_action,
            "score": comment_obj.score,
            "reasons": comment_obj.reasons,
            "lead": lead_result
        }

    def approve_review_item(
        self,
        review_id: str,
        reviewer_id: str = "staff_sale_1",
        phone_override: Optional[str] = None,
        note_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Nhân viên sale bấm Duyệt 1 bình luận trong hàng chờ để chuyển thành Lead."""
        review_item = self.review_queue_db.get(review_id)
        if not review_item:
            raise ValueError(f"Không tìm thấy mục hàng duyệt {review_id}")
        if review_item.status != ReviewStatusEnum.PENDING:
            raise ValueError('Mục này đã được xử lý.')

        comment = self.comments_db.get(review_item.comment_id)
        if not comment:
            raise ValueError(f"Không tìm thấy bình luận nguồn {review_item.comment_id}")

        review_item.reviewer_id = reviewer_id
        review_item.reviewer_note = note_override or "Sale duyệt thủ công từ hàng chờ"
        review_item.reviewed_at = utc_now_iso()

        # Tạo lead trên Revoland
        lead_sync = self.revoland_client.create_or_update_lead(
            listing_id=comment.listing_id or "LISTING_GENERAL",
            customer_name=comment.fb_user_name,
            phone_number=phone_override,
            fb_user_id=comment.fb_user_id,
            fb_comment_id=comment.id,
            note=f"[Staff Approved] Duyệt bởi {reviewer_id}. Ghi chú: {review_item.reviewer_note}"
        )

        if not lead_sync.get('success'):
            return {'success': False, 'message': 'Chưa tạo được lead trên Revoland; mục vẫn ở hàng chờ.', 'lead': None}
        review_item.status = ReviewStatusEnum.APPROVED

        lead_id = f"lead_{uuid.uuid4().hex[:8]}"
        lead_obj = RevolandLead(
            id=lead_id,
            revoland_lead_id=lead_sync.get("revoland_lead_id"),
            comment_id=comment.id,
            listing_id=comment.listing_id,
            customer_name=comment.fb_user_name,
            phone_number=phone_override,
            intent_summary=f"Nhân viên {reviewer_id} duyệt: {comment.raw_content}",
            sync_status="synced" if lead_sync.get("success") else "failed",
            revoland_response=lead_sync
        )
        self.leads_db[lead_id] = lead_obj

        return {
            "success": True,
            "message": "Đã duyệt và tạo Lead Revoland thành công",
            "lead": lead_obj.model_dump()
        }

    def reject_review_item(self, review_id: str, reviewer_id: str = "staff_sale_1", reason: str = "Không tiềm năng") -> Dict[str, Any]:
        """Nhân viên sale bấm Bỏ qua 1 bình luận trong hàng chờ."""
        review_item = self.review_queue_db.get(review_id)
        if not review_item:
            raise ValueError(f"Không tìm thấy mục hàng duyệt {review_id}")

        review_item.status = ReviewStatusEnum.REJECTED
        review_item.reviewer_id = reviewer_id
        review_item.reviewer_note = reason
        review_item.reviewed_at = utc_now_iso()

        return {
            "success": True,
            "message": f"Đã loại bỏ bình luận khỏi hàng chờ duyệt ({reason})",
            "review_id": review_id
        }

    def list_review_queue(self, status: Optional[str] = "pending") -> List[Dict[str, Any]]:
        """Lấy danh sách hàng chờ duyệt kèm thông tin bình luận gốc."""
        results = []
        for r_id, item in self.review_queue_db.items():
            if status and item.status.value != status:
                continue
            comment = self.comments_db.get(item.comment_id)
            results.append({
                "review_id": r_id,
                "status": item.status.value,
                "comment_id": item.comment_id,
                "customer_name": comment.fb_user_name if comment else "",
                "comment_text": comment.raw_content if comment else "",
                "score": comment.score if comment else 0.0,
                "reasons": comment.reasons if comment else [],
                "created_at": item.created_at
            })
        return results

    def list_leads(self) -> List[Dict[str, Any]]:
        return [lead.model_dump() for lead in self.leads_db.values()]
