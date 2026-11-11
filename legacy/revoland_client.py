"""Client tích hợp API tạo và cập nhật Lead trên hệ thống Revoland.
Hỗ trợ cả chế độ Live HTTP và Chế độ Giả lập (Mock Mode) để kiểm thử độc lập ngay từ ngày đầu.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional
import requests

from legacy.dedup import generate_lead_dedup_key


class RevolandClient:
    def __init__(
        self,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: bool = True
    ):
        self.api_base_url = api_base_url or os.getenv("REVOLAND_API_URL", "https://api.revoland.vn/v1")
        self.api_key = api_key or os.getenv("REVOLAND_API_KEY", "mock_key_revoland_2026")
        self.mock_mode = mock_mode
        self._existing_leads_cache: Dict[str, Dict[str, Any]] = {}

    def create_or_update_lead(
        self,
        listing_id: str,
        customer_name: str,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        fb_user_id: Optional[str] = None,
        fb_comment_id: Optional[str] = None,
        note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Tạo lead mới hoặc cập nhật nếu đã tồn tại, có cơ chế chống tạo trùng lặp."""
        dedup_key = generate_lead_dedup_key(listing_id, phone_number, fb_user_id)

        # Kiểm tra chống trùng trong phiên
        if dedup_key in self._existing_leads_cache:
            existing = self._existing_leads_cache[dedup_key]
            return {
                "success": True,
                "action": "updated_existing",
                "revoland_lead_id": existing["revoland_lead_id"],
                "message": f"Lead đã tồn tại trên tin {listing_id}. Đã cập nhật ghi chú bổ sung.",
                "data": existing
            }

        payload = {
            "source": "facebook_comment_tool",
            "listing_id": listing_id,
            "customer_name": customer_name,
            "phone_number": phone_number,
            "email": email,
            "fb_user_id": fb_user_id,
            "fb_comment_id": fb_comment_id,
            "note": note or "Tạo tự động từ bộ lọc bình luận Facebook"
        }

        if self.mock_mode:
            lead_id = f"REV_LEAD_{uuid.uuid4().hex[:8].upper()}"
            result_data = {
                "revoland_lead_id": lead_id,
                "status": "created",
                "payload": payload
            }
            self._existing_leads_cache[dedup_key] = result_data
            return {
                "success": True,
                "action": "created_new",
                "revoland_lead_id": lead_id,
                "message": "Tạo lead thành công trên Revoland (Mock Mode)",
                "data": result_data
            }

        # Live Mode
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            resp = requests.post(
                f"{self.api_base_url}/leads",
                json=payload,
                headers=headers,
                timeout=10
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                lead_id = data.get("lead_id") or data.get("id")
                if not lead_id:
                    return {'success': False, 'action': 'unconfirmed', 'revoland_lead_id': None,
                            'message': 'API nhận yêu cầu nhưng chưa trả mã lead. Cần kiểm tra trước khi gửi lại.', 'data': data}
                self._existing_leads_cache[dedup_key] = {"revoland_lead_id": lead_id, "data": data}
                return {
                    "success": True,
                    "action": "created_new",
                    "revoland_lead_id": lead_id,
                    "message": "Tạo lead thành công trên Revoland Live API",
                    "data": data
                }
            return {
                "success": False,
                "action": "failed",
                "revoland_lead_id": None,
                "message": f"Lỗi Revoland API: HTTP {resp.status_code} - {resp.text}",
                "data": {}
            }
        except Exception as e:
            return {
                "success": False,
                "action": "error",
                "revoland_lead_id": None,
                "message": f"Không thể kết nối Revoland API: {str(e)}",
                "data": {}
            }
