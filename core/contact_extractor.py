"""Module trích xuất thông tin liên hệ (Số điện thoại, Zalo, Email) từ bình luận Facebook.
Xử lý đặc thù người Việt hay viết số điện thoại cách dấu chấm, dấu cách, số 0 đầu, +84, v.v.
"""
from __future__ import annotations

import re
from typing import Dict, Optional


# Regex nhận diện số điện thoại di động Việt Nam:
# Đầu số hợp lệ:
# Viettel: 086, 096, 097, 098, 032, 033, 034, 035, 036, 037, 038, 039
# Mobifone: 089, 090, 093, 070, 079, 077, 076, 078
# Vinaphone: 088, 091, 094, 083, 084, 085, 081, 082
# Vietnamobile: 092, 056, 058
# Gmobile: 099, 059
# Itelecom, Wintel: 087, 055
VN_MOBILE_PREFIXES = (
    "086", "096", "097", "098", "032", "033", "034", "035", "036", "037", "038", "039",
    "089", "090", "093", "070", "079", "077", "076", "078",
    "088", "091", "094", "083", "084", "085", "081", "082",
    "092", "056", "058", "099", "059", "087", "055"
)

# Regex tìm kiếm chuỗi số điện thoại Việt Nam (10 chữ số với các biến thể phân tách bằng dấu chấm, gạch ngang, khoảng trắng)
PHONE_PATTERN = re.compile(
    r'(?:(?:\+84|84|0)(?:[\s\.\-]?\d){9}\b)'
)

# Regex tìm Email
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
)

# Regex tìm Zalo
ZALO_MENTION_PATTERN = re.compile(
    r'(?:zalo|zl)\s*[:\-\s]?\s*([0-9\.\-\s]{9,15}|https?://zalo\.me/\S+)',
    re.IGNORECASE
)


def normalize_phone(raw_phone: str) -> Optional[str]:
    """Làm sạch và chuẩn hóa số điện thoại về định dạng chuẩn 10 chữ số (0xxxxxxxxx)."""
    if not raw_phone:
        return None
    
    # Loại bỏ mọi ký tự không phải số hoặc dấu +
    digits = re.sub(r'[^\d+]', '', raw_phone)
    if digits.startswith('+84'):
        digits = '0' + digits[3:]
    elif digits.startswith('84') and len(digits) == 11:
        digits = '0' + digits[2:]
        
    # Số điện thoại di động VN chuẩn hiện nay có đúng 10 số, bắt đầu bằng 0
    if len(digits) == 10 and digits.startswith('0'):
        prefix = digits[:3]
        if prefix in VN_MOBILE_PREFIXES:
            return digits
    return None


def extract_contacts(text: str) -> Dict[str, any]:
    """Trích xuất tất cả số điện thoại, email, thông tin zalo từ văn bản."""
    if not text:
        return {
            "phones": [],
            "primary_phone": None,
            "emails": [],
            "zalo": None,
            "has_contact": False
        }

    extracted_phones = []
    # 1. Tìm theo phone pattern
    matches = PHONE_PATTERN.findall(text)
    for match in matches:
        norm = normalize_phone(match)
        if norm and norm not in extracted_phones:
            extracted_phones.append(norm)

    # 2. Tìm theo Zalo pattern
    zalo_info = None
    zalo_match = ZALO_MENTION_PATTERN.search(text)
    if zalo_match:
        zalo_val = zalo_match.group(1).strip()
        zalo_phone = normalize_phone(zalo_val)
        if zalo_phone:
            zalo_info = zalo_phone
            if zalo_phone not in extracted_phones:
                extracted_phones.append(zalo_phone)
        else:
            zalo_info = zalo_val

    # 3. Tìm email
    emails = EMAIL_PATTERN.findall(text)

    primary_phone = extracted_phones[0] if extracted_phones else None
    has_contact = bool(primary_phone or emails or zalo_info)

    return {
        "phones": extracted_phones,
        "primary_phone": primary_phone,
        "emails": emails,
        "zalo": zalo_info,
        "has_contact": has_contact
    }
