"""Module chống xử lý trùng lặp bình luận và lead (De-duplication).
Ngăn chặn:
- Tiếp nhận 1 bình luận nhiều lần khi webhook/crawler chạy lại.
- Tạo nhiều lead trùng cho cùng 1 số điện thoại / Facebook user trên cùng 1 tin đăng.
"""
from __future__ import annotations

import hashlib
from typing import Optional


def generate_comment_hash(post_id: str, fb_user_id: str, clean_text: str) -> str:
    """Tạo mã băm MD5 duy nhất cho một bình luận để phát hiện trùng lặp nội dung."""
    payload = f"{post_id}|{fb_user_id}|{clean_text.strip().lower()}"
    return hashlib.md5(payload.encode('utf-8')).hexdigest()


def generate_lead_dedup_key(listing_id: str, phone: Optional[str] = None, fb_user_id: Optional[str] = None) -> str:
    """Tạo khóa chống trùng cho lead dựa trên tin đăng và thông tin khách hàng."""
    if phone:
        return f"lead:{listing_id}:phone:{phone}"
    if fb_user_id:
        return f"lead:{listing_id}:fb:{fb_user_id}"
    return f"lead:{listing_id}:unknown"
