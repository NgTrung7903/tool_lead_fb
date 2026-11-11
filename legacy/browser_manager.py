"""Module tự động hóa trình duyệt (Playwright) hỗ trợ:
1. Đăng nhập Facebook (lưu profile & cookie phiên đăng nhập).
2. Truy cập các nhóm/bài viết Facebook hoặc website rao vặt để cào bình luận và nội dung.
3. Đăng nhập website Revoland để trích xuất tin đăng hoặc khách hàng liên hệ.
4. Tự động chuyển toàn bộ dữ liệu cào được qua bộ lọc Registry Engine và xuất ra file Excel.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright

from core.filter_engine import RegistryFilterEngine
from services.excel_exporter import export_records_to_excel


USER_DATA_DIR = Path(__file__).resolve().parent.parent / "browser_data"
FB_PROFILE_DIR = USER_DATA_DIR / "fb_profile"
REVOLAND_PROFILE_DIR = USER_DATA_DIR / "revoland_profile"


class BrowserLeadManager:
    def __init__(self, filter_engine: Optional[RegistryFilterEngine] = None):
        self.filter_engine = filter_engine or RegistryFilterEngine()
        FB_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        REVOLAND_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    def open_facebook_login(self, headless: bool = False) -> Dict[str, Any]:
        """Mở trình duyệt trực quan để người dùng đăng nhập Facebook một lần.
        Dữ liệu phiên được lưu trong FB_PROFILE_DIR; Facebook có thể yêu cầu đăng nhập/xác minh lại.
        """
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(FB_PROFILE_DIR),
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.goto("https://www.facebook.com/", timeout=60000)
                # Cho người dùng thời gian thao tác nếu mở cửa sổ tương tác
                if not headless:
                    print("Trình duyệt Facebook đã mở. Người dùng đăng nhập tài khoản...")
                    # Chờ tối đa 60 giây hoặc cho đến khi phát hiện đã vào trang chủ (có feed)
                    try:
                        page.wait_for_timeout(30000)
                    except Exception:
                        pass
                context.close()
            return {
                "success": True,
                "message": "Đã lưu phiên đăng nhập Facebook vào thư mục profile.",
                "profile_path": str(FB_PROFILE_DIR)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Lỗi mở Facebook: {str(e)}"
            }

    def open_revoland_login(self, revoland_url: str = "https://revoland.vn", headless: bool = False) -> Dict[str, Any]:
        """Mở trình duyệt để người dùng đăng nhập vào hệ thống website Revoland."""
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(REVOLAND_PROFILE_DIR),
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800}
                )
                page = context.new_page()
                page.goto(revoland_url, timeout=60000)
                if not headless:
                    print(f"Trình duyệt Revoland ({revoland_url}) đã mở...")
                    try:
                        page.wait_for_timeout(30000)
                    except Exception:
                        pass
                context.close()
            return {
                "success": True,
                "message": "Đã lưu phiên đăng nhập Revoland.",
                "profile_path": str(REVOLAND_PROFILE_DIR)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Lỗi mở Revoland: {str(e)}"
            }

    def crawl_and_extract_comments(
        self,
        target_url: str,
        site_type: str = "facebook",
        max_items: int = 30,
        headless: bool = True
    ) -> List[Dict[str, Any]]:
        """Truy cập URL mục tiêu (Facebook hoặc Revoland hoặc web BĐS), cào nội dung text."""
        extracted_items = []
        profile_dir = FB_PROFILE_DIR if site_type == "facebook" else REVOLAND_PROFILE_DIR

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            try:
                page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(3)  # Chờ script mạng tải hoàn tất

                # Tự động cuộn xuống để kích hoạt lazy loading
                for _ in range(3):
                    page.mouse.wheel(0, 1500)
                    time.sleep(1.5)

                if site_type == "facebook":
                    # Tìm các block bình luận trên Facebook (hỗ trợ cả giao diện mới và cũ)
                    # Facebook thường bọc bình luận trong div role="article" hoặc dir="auto"
                    comments_elements = page.query_selector_all('div[role="article"], div[dir="auto"]')
                    seen_texts = set()

                    for el in comments_elements:
                        try:
                            txt = el.inner_text().strip()
                            if len(txt) > 3 and txt not in seen_texts:
                                seen_texts.add(txt)
                                lines = [l.strip() for l in txt.splitlines() if l.strip()]
                                author = lines[0] if len(lines) > 1 else "Khách Facebook"
                                comment_body = "\n".join(lines[1:]) if len(lines) > 1 else txt

                                extracted_items.append({
                                    "id": f"fb_crawl_{len(extracted_items)+1:03d}",
                                    "author": author,
                                    "text": comment_body,
                                    "source_url": target_url,
                                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                                })
                                if len(extracted_items) >= max_items:
                                    break
                        except Exception:
                            continue

                else:
                    # Website Revoland hoặc BĐS tổng quát
                    elements = page.query_selector_all('p, .comment, .review, .inquiry, .contact-content')
                    seen_texts = set()
                    for el in elements:
                        try:
                            txt = el.inner_text().strip()
                            if len(txt) > 10 and txt not in seen_texts:
                                seen_texts.add(txt)
                                extracted_items.append({
                                    "id": f"rev_crawl_{len(extracted_items)+1:03d}",
                                    "author": "Khách Revoland Web",
                                    "text": txt,
                                    "source_url": target_url,
                                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                                })
                                if len(extracted_items) >= max_items:
                                    break
                        except Exception:
                            continue

            except Exception as e:
                print(f"Lỗi khi cào URL {target_url}: {e}")
            finally:
                context.close()

        return extracted_items

    def process_and_export_leads(
        self,
        raw_items: List[Dict[str, Any]],
        output_excel_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Đưa danh sách thô cào được qua bộ lọc Registry, chia field và xuất ra file Excel."""
        if not output_excel_path:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_excel_path = str(Path(__file__).resolve().parent.parent / "data" / f"leads_export_{timestamp}.xlsx")

        processed_records = []
        lead_potential_count = 0
        needs_review_count = 0
        ignore_count = 0

        for item in raw_items:
            text = item.get("text", "")
            eval_res = self.filter_engine.evaluate(text)

            record = {
                "id": item.get("id"),
                "classification": eval_res["classification"],
                "score": eval_res["score"],
                "phone_number": eval_res["contacts"].get("primary_phone") or "",
                "fb_user_name": item.get("author") or "Khách hàng",
                "email": eval_res["contacts"]["emails"][0] if eval_res["contacts"].get("emails") else "",
                "contacts": eval_res["contacts"],
                "reasons": eval_res["reasons"],
                "signals": eval_res["signals"],
                "raw_content": text,
                "source_url": item.get("source_url") or "Trang web",
                "created_at": item.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }

            if eval_res["classification"] == "LEAD_POTENTIAL":
                lead_potential_count += 1
            elif eval_res["classification"] == "NEEDS_REVIEW":
                needs_review_count += 1
            else:
                ignore_count += 1

            processed_records.append(record)

        # Xuất file Excel với các cột chia rõ ràng
        saved_file = export_records_to_excel(processed_records, output_excel_path)

        return {
            "success": True,
            "total_items": len(processed_records),
            "lead_potential_count": lead_potential_count,
            "needs_review_count": needs_review_count,
            "ignore_count": ignore_count,
            "excel_path": saved_file,
            "records": processed_records
        }
