"""Mô hình dữ liệu Pydantic v2 cho Tool Đăng Tin BĐS Lên Nhóm Facebook Bằng Phiên Trình Duyệt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GroupPostStatusEnum(str, Enum):
    PENDING = "pending"                     # Đang chờ xử lý
    RUNNING = "running"                     # Đang đăng bài
    POSTED = "posted"                       # Đã đăng thành công trên feed nhóm
    PENDING_APPROVAL = "pending_approval"   # Đã gửi bài, đang chờ Quản trị viên nhóm phê duyệt
    FAILED = "failed"                       # Đăng thất bại (bị hạn chế, lỗi mạng, lỗi giao diện)
    ACTION_REQUIRED = "action_required"     # Cần khách hàng can thiệp (hết phiên đăng nhập, checkpoint)
    SKIPPED_DUPLICATE = "skipped_duplicate" # Bỏ qua do đã đăng thành công trước đó (Chống đăng trùng)
    UNKNOWN = "unknown"  # Đã bắt đầu gửi nhưng chưa xác nhận; không tự retry


class RevolandConfig(BaseModel):
    revoland_api_url: str = Field(default="https://api.revoland.vn/v1", description="Endpoint API Revoland")
    revoland_api_key: str = Field(default="mock_revoland_api_key_2026", description="API Key xác thực")
    revoland_mock_mode: bool = Field(default=True, description="Chế độ giả lập khi chưa có API thật")
    contact_phone: str = Field(default="0912.345.678", description="Số điện thoại đính kèm trong bài đăng")
    contact_name: str = Field(default="Chuyên Viên Tư Vấn Revoland", description="Tên người liên hệ")


class PropertyListing(BaseModel):
    id: str = Field(..., description="ID định danh căn trên Revoland")
    code: str = Field(..., description="Mã căn (VD: REV-VH-01)")
    title: str = Field(..., description="Tiêu đề căn hộ/nhà đất")
    property_type: Optional[str] = Field(default="Căn hộ", description="Loại BĐS (Căn hộ, Nhà phố, Đất nền...)")
    price_text: str = Field(..., description="Giá hiển thị (VD: 2.85 Tỷ)")
    area_m2: Optional[float] = Field(default=None, description="Diện tích (m2)")
    location: str = Field(..., description="Khu vực / Địa chỉ")
    bedrooms: Optional[int] = Field(default=None, description="Số phòng ngủ")
    bathrooms: Optional[int] = Field(default=None, description="Số phòng vệ sinh")
    description: str = Field(..., description="Mô tả chi tiết đặc điểm căn")
    media_urls: List[str] = Field(default_factory=list, description="Danh sách URL hình ảnh thực tế")
    revoland_url: Optional[str] = Field(None, description="Đường dẫn xem chi tiết trên web Revoland")
    status: str = Field(default="available", description="Trạng thái căn (available, sold, reserved)")
    legal_status: Optional[str] = None


class FBGroup(BaseModel):
    id: str = Field(..., description="Mã nhóm trong hệ thống")
    name: str = Field(..., description="Tên nhóm Facebook")
    group_url: str = Field(..., description="Đường dẫn URL nhóm Facebook")
    category: Optional[str] = Field(None, description="Phân loại khu vực (VD: BĐS Thủ Đức, Quận 7...)")
    status: str = Field(default="active", description="active | paused")
    notes: Optional[str] = None
    # Compatibility for the deferred manual-assisted lead pipeline.
    fb_group_id: Optional[str] = None
    posting_mode: str = "manual_assisted"


class GroupTaskResult(BaseModel):
    task_id: str
    group_id: str
    group_name: str
    group_url: str
    status: GroupPostStatusEnum = GroupPostStatusEnum.PENDING
    post_url: Optional[str] = None
    error_message: Optional[str] = None
    posted_at: Optional[str] = None
    retry_count: int = 0
    evidence: Optional[str] = None
    submission_started: bool = False
    post_check_status: Literal['unchecked', 'available', 'unavailable', 'action_required', 'unknown'] = 'unchecked'
    post_checked_at: Optional[str] = None
    post_check_message: Optional[str] = None
    attempt_history: List[Dict[str, Any]] = Field(default_factory=list)


class PostingCampaign(BaseModel):
    id: str = Field(..., description="Mã chiến dịch đăng bài")
    listing_id: str
    listing_title: str
    formatted_content: str
    media_urls: List[str] = Field(default_factory=list)
    min_delay_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    max_delay_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    total_groups: int = 0
    tasks: List[GroupTaskResult] = Field(default_factory=list)
    status: str = Field(default="created", description="created | running | completed | partial_failed")
    created_at: str = Field(default_factory=utc_now_iso)
    source_mode: str = "live"
    source_url: Optional[str] = None
    error_message: Optional[str] = None


class SessionStatus(BaseModel):
    is_authenticated: bool
    status_text: str
    user_name: Optional[str] = None
    profile_dir: str
    checked_at: str = Field(default_factory=utc_now_iso)
    busy: bool = False
    login_in_progress: bool = False
    login_result: Optional[Dict[str, Any]] = None


# Deferred features retain their data contract without coupling them to posting.
class Listing(BaseModel):
    id: str
    revoland_listing_id: Optional[str] = None
    title: str
    content: str
    price_text: Optional[str] = None
    location_text: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)


class PostingStatusEnum(str, Enum):
    PENDING = "pending"
    MANUAL_READY = "manual_ready"
    POSTED = "posted"


class PostingTask(BaseModel):
    id: str
    listing_id: str
    group_id: str
    status: PostingStatusEnum = PostingStatusEnum.PENDING
    post_url: Optional[str] = None
    post_fb_id: Optional[str] = None
    posted_at: Optional[str] = None


class ClassificationEnum(str, Enum):
    LEAD_POTENTIAL = "LEAD_POTENTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORE = "IGNORE"


class FBComment(BaseModel):
    id: str
    posting_task_id: Optional[str] = None
    listing_id: Optional[str] = None
    fb_comment_id: Optional[str] = None
    fb_user_id: str
    fb_user_name: str
    raw_content: str
    source_type: str
    classification: ClassificationEnum
    score: float
    reasons: List[str] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)


class ReviewStatusEnum(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewItem(BaseModel):
    id: str
    comment_id: str
    status: ReviewStatusEnum = ReviewStatusEnum.PENDING
    reviewer_id: Optional[str] = None
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=utc_now_iso)


class RevolandLead(BaseModel):
    id: str
    revoland_lead_id: Optional[str] = None
    comment_id: str
    listing_id: Optional[str] = None
    customer_name: str
    phone_number: Optional[str] = None
    email: Optional[str] = None
    intent_summary: str
    sync_status: str
    revoland_response: Dict[str, Any] = Field(default_factory=dict)
