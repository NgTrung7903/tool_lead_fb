"""Service quản lý nhóm Facebook và tác vụ phân phối tin (Posting Task).
Hỗ trợ chiến lược tích hợp kép (Dual-track):
1. Chế độ Tự Động (Auto Graph API): Dùng khi có access token và quyền group.
2. Chế độ Bán Tự Động (Manual-Assisted): Hỗ trợ người dùng 1 nút copy nội dung & mở link nhóm,
   sau đó lưu lại Post URL / ID để theo dõi bình luận.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from models.schema import FBGroup, Listing, PostingStatusEnum, PostingTask, utc_now_iso


class FacebookService:
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("FB_ACCESS_TOKEN")
        self._groups_db: Dict[str, FBGroup] = {}
        self._tasks_db: Dict[str, PostingTask] = {}
        self._init_default_groups()

    def _init_default_groups(self) -> None:
        """Khởi tạo một số nhóm mẫu bất động sản."""
        sample_groups = [
            FBGroup(
                id="grp_001",
                fb_group_id="123456789012345",
                name="Bất Động Sản TP. Thủ Đức - Sài Gòn",
                group_url="https://facebook.com/groups/bds.thuduc",
                posting_mode="manual_assisted",
                status="active"
            ),
            FBGroup(
                id="grp_002",
                fb_group_id="987654321098765",
                name="Hội Mua Bán Nhà Đất Chính Chủ TP.HCM",
                group_url="https://facebook.com/groups/nhadat.hcm",
                posting_mode="manual_assisted",
                status="active"
            ),
            FBGroup(
                id="grp_003",
                fb_group_id="555666777888999",
                name="Cộng Đồng Bất Động Sản Quận 7 - Nhà Bè",
                group_url="https://facebook.com/groups/bds.quan7",
                posting_mode="manual_assisted",
                status="active"
            )
        ]
        for g in sample_groups:
            self._groups_db[g.id] = g

    def list_groups(self) -> List[FBGroup]:
        return list(self._groups_db.values())

    def add_group(self, name: str, group_url: str, fb_group_id: Optional[str] = None, posting_mode: str = "manual_assisted") -> FBGroup:
        gid = f"grp_{uuid.uuid4().hex[:6]}"
        group = FBGroup(
            id=gid,
            fb_group_id=fb_group_id,
            name=name,
            group_url=group_url,
            posting_mode=posting_mode,
            status="active"
        )
        self._groups_db[gid] = group
        return group

    def create_distribution_campaign(self, listing: Listing, target_group_ids: List[str]) -> List[PostingTask]:
        """Tạo các tác vụ đăng bài cho tin vào các nhóm được chọn."""
        created_tasks = []
        for gid in target_group_ids:
            if gid not in self._groups_db:
                continue
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            task = PostingTask(
                id=task_id,
                listing_id=listing.id,
                group_id=gid,
                status=PostingStatusEnum.MANUAL_READY if self._groups_db[gid].posting_mode == "manual_assisted" else PostingStatusEnum.PENDING
            )
            self._tasks_db[task_id] = task
            created_tasks.append(task)
        return created_tasks

    def get_assisted_post_payload(self, task_id: str, listing: Listing) -> Dict[str, Any]:
        """Tạo dữ liệu hỗ trợ đăng bài (Payload để copy và mở nhanh nhóm)."""
        task = self._tasks_db.get(task_id)
        if not task:
            raise ValueError(f"Không tìm thấy tác vụ {task_id}")
        group = self._groups_db.get(task.group_id)
        if not group:
            raise ValueError(f"Không tìm thấy nhóm {task.group_id}")

        formatted_post_text = (
            f"🏡 {listing.title}\n"
            f"📍 Khu vực: {listing.location_text or 'TP.HCM'}\n"
            f"💰 Giá: {listing.price_text or 'Thương lượng'}\n"
            f"------------------------\n"
            f"{listing.content}\n"
            f"------------------------\n"
            f"☎️ Liên hệ xem nhà ngay / Nhắn tin để nhận thông tin chi tiết!"
        )

        return {
            "task_id": task_id,
            "group_name": group.name,
            "group_url": group.group_url,
            "formatted_text": formatted_post_text,
            "media_urls": listing.media_urls,
            "action": "Copy nội dung, mở link nhóm trên trình duyệt để đăng bài"
        }

    def mark_task_posted(self, task_id: str, post_url: Optional[str] = None, post_fb_id: Optional[str] = None) -> PostingTask:
        """Cập nhật trạng thái tác vụ sau khi người dùng hoặc tool đăng xong."""
        task = self._tasks_db.get(task_id)
        if not task:
            raise ValueError(f"Không tìm thấy tác vụ {task_id}")
        task.status = PostingStatusEnum.POSTED
        task.post_url = post_url
        task.post_fb_id = post_fb_id or f"fb_post_{uuid.uuid4().hex[:8]}"
        task.posted_at = utc_now_iso()
        return task
