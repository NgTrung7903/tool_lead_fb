"""Service kết nối API Revoland: Lấy danh sách căn đã đăng, chi tiết giá/ảnh,
kiểm tra kết nối và định dạng bài đăng cho nhóm Facebook.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import requests
import hashlib
import io
import uuid
from PIL import Image, ImageOps

from config.settings import TEMP_IMAGE_DIR, load_config
from models.schema import PropertyListing, RevolandConfig


SAMPLE_LISTINGS: List[Dict[str, Any]] = [
    {
        "id": "rev_listing_001",
        "code": "VH-GP-2PN-72",
        "title": "Bán gấp căn 2PN 2WC Vinhomes Grand Park, view thoáng mát công viên 36ha",
        "property_type": "Căn hộ cao cấp",
        "price_text": "2.85 Tỷ (Bao thuế phí)",
        "area_m2": 72.0,
        "location": "Phường Long Bình, TP. Thủ Đức, TP.HCM",
        "bedrooms": 2,
        "bathrooms": 2,
        "description": "Căn hộ tầng trung toà Origami view nội khu hoa anh đào. Đã trang bị full nội thất cao cấp: sofa da, giường tủ An Cường, 3 máy lạnh Daikin, bếp từ Bosch. Sổ hồng chuẩn chỉnh, sang tên công chứng ngay. Ngân hàng hỗ trợ vay 70% với lãi suất ưu đãi.",
        "media_urls": [
            "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800",
            "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800"
        ],
        "revoland_url": "https://revoland.vn/bds/VH-GP-2PN-72",
        "status": "available"
    },
    {
        "id": "rev_listing_002",
        "code": "MV-Q7-1PN-50",
        "title": "Căn hộ 1PN Midtown Phú Mỹ Hưng, đầy đủ tiện nghi, giá tốt đầu tư",
        "property_type": "Căn hộ cao cấp",
        "price_text": "3.95 Tỷ",
        "area_m2": 54.0,
        "location": "Khu đô thị Phú Mỹ Hưng, Quận 7, TP.HCM",
        "bedrooms": 1,
        "bathrooms": 1,
        "description": "Căn hộ đẹp phong cách Nhật Bản ven sông Cả Cấm. Tiện ích chuẩn resort: hồ bơi tràn bờ, phòng gym, công viên hoa anh đào Sakura Park. Đang có hợp đồng thuê chuyên gia nước ngoài 18 triệu/tháng.",
        "media_urls": [
            "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=800",
            "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800"
        ],
        "revoland_url": "https://revoland.vn/bds/MV-Q7-1PN-50",
        "status": "available"
    },
    {
        "id": "rev_listing_003",
        "code": "NP-GV-5X18",
        "title": "Nhà phố 1 trệt 3 lầu hẻm xe hơi 6m đường Quang Trung, Gò Vấp",
        "property_type": "Nhà phố riêng lẻ",
        "price_text": "7.2 Tỷ (Thương lượng chính chủ)",
        "area_m2": 90.0,
        "location": "Đường Quang Trung, Phường 8, Quận Gò Vấp, TP.HCM",
        "bedrooms": 4,
        "bathrooms": 5,
        "description": "Nhà mới xây đúc kiên cố BTCT, gara để được xe 7 chỗ. Khu dân trí cao, an ninh, gần chợ Hạnh Thông Tây, bệnh viện Gò Vấp. Sổ hồng hoàn công đầy đủ, pháp lý sạch không quy hoạch.",
        "media_urls": [
            "https://images.unsplash.com/photo-1600585154526-990dced4db0d?w=800"
        ],
        "revoland_url": "https://revoland.vn/bds/NP-GV-5X18",
        "status": "available"
    }
]


class RevolandAPIError(RuntimeError):
    pass


class RevolandService:
    def __init__(self):
        self.config = load_config()

    def update_config(self, new_cfg: Dict[str, Any]) -> RevolandConfig:
        for k, v in new_cfg.items():
            if k in self.config:
                self.config[k] = v
        from config.settings import save_config
        save_config(self.config)
        return RevolandConfig(**self.config)

    def test_connection(self) -> Dict[str, Any]:
        """Kiểm tra kết nối tới Revoland API."""
        if self.config.get("revoland_mock_mode", True):
            return {
                "success": True,
                "mode": "mock",
                "message": "Kết nối thành công (Chế độ Revoland Mock Data hoạt động ổn định).",
                "status_code": 200
            }

        url = f"{self.config.get('revoland_api_url').rstrip('/')}/ping"
        headers = {"Authorization": f"Bearer {self.config.get('revoland_api_key')}"}
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code in [200, 204]:
                return {
                    "success": True,
                    "mode": "live",
                    "message": "Kết nối thành công tới Revoland Live API.",
                    "status_code": resp.status_code
                }
            return {
                "success": False,
                "mode": "live",
                "message": f"Revoland API trả về mã lỗi: HTTP {resp.status_code}",
                "status_code": resp.status_code
            }
        except Exception as e:
            return {
                "success": False,
                "mode": "live",
                "message": "Không thể kết nối máy chủ Revoland. Kiểm tra URL, API key và mạng.",
                "status_code": 0
            }

    def get_listings(self) -> List[PropertyListing]:
        """Lấy danh sách các căn hộ/nhà đất đã đăng trên Revoland."""
        if self.config.get("revoland_mock_mode", True):
            return [PropertyListing(**item) for item in SAMPLE_LISTINGS]

        url = f"{self.config.get('revoland_api_url').rstrip('/')}/listings"
        headers = {"Authorization": f"Bearer {self.config.get('revoland_api_key')}"}
        try:
            listings = []
            page = 1
            while page <= 100:
                resp = requests.get(url, headers=headers, params={"page": page}, timeout=12)
                if resp.status_code != 200:
                    raise RevolandAPIError(f'Revoland trả HTTP {resp.status_code}; không sử dụng dữ liệu mẫu thay thế.')
                raw = resp.json()
                items = raw if isinstance(raw, list) else raw.get('data', raw.get('listings'))
                if isinstance(items, dict):
                    items = items.get('items', items.get('data'))
                if not isinstance(items, list):
                    raise RevolandAPIError('Dữ liệu Revoland không đúng hợp đồng API (cần mảng căn).')
                listings.extend(PropertyListing(**item) for item in items)
                meta = raw.get('meta', raw) if isinstance(raw, dict) else {}
                last_page = int(meta.get('last_page', 1))
                if page >= last_page:
                    return list({item.id: item for item in listings}.values())
                page += 1
            raise RevolandAPIError('API vượt giới hạn 100 trang; hãy thu hẹp tập dữ liệu.')
        except RevolandAPIError:
            raise
        except Exception as e:
            raise RevolandAPIError('Không thể tải căn từ Revoland. Kiểm tra kết nối và hợp đồng dữ liệu API.') from e

    def get_listing_by_id(self, listing_id: str) -> Optional[PropertyListing]:
        listings = self.get_listings()
        for item in listings:
            if item.id == listing_id:
                return item
        return None

    def format_post_content(self, listing: PropertyListing) -> str:
        """Định dạng bài viết chuẩn chuyên nghiệp cho hội nhóm Facebook BĐS."""
        phone = self.config.get("contact_phone", "0912.345.678")
        contact_name = self.config.get("contact_name", "Chuyên Viên Tư Vấn")

        room_parts = [
            *([f"{listing.bedrooms} Phòng ngủ"] if listing.bedrooms is not None else []),
            *([f"{listing.bathrooms} WC"] if listing.bathrooms is not None else []),
        ]
        spec_lines = []
        if listing.area_m2:
            suffix = f" ({', '.join(room_parts)})" if room_parts else ""
            spec_lines.append(f"📐 Diện tích: {listing.area_m2} m²{suffix}")
        elif room_parts:
            spec_lines.append(f"🛏️ Kết cấu: {', '.join(room_parts)}")

        lines = [
            f"🏡 {listing.title.upper()}",
            f"━━━━━━━━━━━━━━━━━━",
            f"📍 Vị trí: {listing.location}",
            f"💰 Giá bán: {listing.price_text}",
            *spec_lines,
            *([f"📋 Pháp lý: {listing.legal_status}"] if listing.legal_status else []),
            f"",
            f"📝 ĐẶC ĐIỂM CHI TIẾT:",
            f"{listing.description}",
            f"",
            f"━━━━━━━━━━━━━━━━━━",
            f"☎️ LIÊN HỆ XEM NHÀ THỰC TẾ 24/7:",
            f"📞 Hotline/Zalo: {phone} ({contact_name})",
            f"🌐 Chi tiết tại Revoland: {listing.revoland_url or 'https://revoland.vn'}",
            f"#Revoland #BatDongSan #NhaDat #BanNha #{re.sub(r'[^a-zA-Z0-9]', '', listing.code)}"
        ]
        return "\n".join(lines)

    def download_listing_images(self, listing: PropertyListing) -> List[str]:
        """Tải các ảnh trong tin về thư mục tạm local để sẵn sàng đính kèm khi đăng bài."""
        saved_paths = []
        # Immutable per-campaign snapshots: later downloads cannot overwrite queued photos.
        listing_dir = TEMP_IMAGE_DIR / hashlib.sha256(listing.id.encode()).hexdigest()[:24] / uuid.uuid4().hex
        listing_dir.mkdir(parents=True, exist_ok=True)

        for url in listing.media_urls:
            local_filename = hashlib.sha256(url.encode()).hexdigest() + '.jpg'
            target_path = listing_dir / local_filename

            try:
                # Refresh content at creation: URL-stable images may change at the origin.
                with requests.get(url, timeout=20, stream=True) as resp:
                    if resp.status_code != 200:
                        raise ValueError('HTTP ' + str(resp.status_code))
                    content = bytearray()
                    for chunk in resp.iter_content(65536):
                        content.extend(chunk)
                        if len(content) > 20 * 1024 * 1024:
                            raise ValueError('Ảnh vượt 20 MB')
                with Image.open(io.BytesIO(content)) as image:
                    ImageOps.exif_transpose(image).convert('RGB').save(target_path, 'JPEG', quality=95)
                saved_paths.append(str(target_path))
            except Exception as e:
                raise RevolandAPIError('Không tải được đầy đủ ảnh của căn. Chưa tạo chiến dịch; hãy kiểm tra ảnh và thử lại.') from e

        return saved_paths
