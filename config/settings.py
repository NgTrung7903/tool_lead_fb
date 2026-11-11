"""Cấu hình toàn hệ thống cho Tool Đăng Bài Facebook Từ Revoland.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parent.parent
# One local customer per process. Separate roots isolate configuration, session and history.
RUNTIME_DIR = Path(os.getenv("REVOLAND_DATA_DIR", str(ROOT_DIR))).resolve()
CONFIG_FILE = RUNTIME_DIR / "config" / "config.json"
PROFILE_DIR = RUNTIME_DIR / "profiles" / "fb_user_profile"
TEMP_IMAGE_DIR = RUNTIME_DIR / "data" / "temp_images"

# Tạo sẵn các thư mục cần thiết
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG: Dict[str, Any] = {
    "revoland_api_url": "https://api.revoland.vn/v1",
    "revoland_api_key": "mock_revoland_api_key_2026",
    "revoland_mock_mode": True,
    "fb_profile_dir": str(PROFILE_DIR),
    "posting_queue_version": 1,
    "min_delay_seconds": 300,
    "max_delay_seconds": 300,
    "max_groups_per_batch": 100,
    "headless_posting": False,
    "contact_phone": "0912.345.678",
    "contact_name": "Chuyên Viên Tư Vấn Revoland"
}


def load_config() -> Dict[str, Any]:
    """Đọc cấu hình từ file config.json, nếu chưa có thì tạo file mặc định."""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        if data.get('posting_queue_version') != 1:
            merged.update(posting_queue_version=1, max_groups_per_batch=100)
        return merged


def save_config(cfg: Dict[str, Any]) -> None:
    """Lưu cấu hình mới vào config.json."""
    from services.storage import atomic_json
    atomic_json(CONFIG_FILE, cfg)
