"""Quản lý danh sách các nhóm Facebook mục tiêu để đăng bài.
Hỗ trợ lưu trữ, thêm mới, sửa, xóa và import danh sách nhóm hàng loạt từ văn bản/link.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import uuid
from typing import Dict, List, Optional

from config.settings import RUNTIME_DIR
from models.schema import FBGroup
from services.storage import atomic_json, ExclusiveOperation
from services.input_errors import InputError
from urllib.parse import urlsplit, unquote


GROUPS_FILE = RUNTIME_DIR / "config" / "groups.json"


def normalize_group_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in ('http', 'https') or parts.hostname not in ('facebook.com', 'www.facebook.com', 'm.facebook.com'):
        raise InputError('Chỉ chấp nhận URL nhóm facebook.com/groups/...', 'group_url')
    match = re.fullmatch(r'/groups/([A-Za-z0-9._-]+)/?', unquote(parts.path))
    if not match or parts.username or parts.password or parts.port:
        raise InputError('URL phải trỏ đến một nhóm Facebook, không phải bài viết.', 'group_url')
    return 'https://www.facebook.com/groups/' + match.group(1).lower()

DEFAULT_GROUPS = [
    {
        "id": "grp_001",
        "name": "BẤT ĐỘNG SẢN TP. THỦ ĐỨC - TP.HCM (Chính Chủ)",
        "group_url": "https://www.facebook.com/groups/bds.thuduc.chinhchu",
        "category": "Thủ Đức",
        "status": "active",
        "notes": "Nhóm cho phép đăng tin căn hộ Vinhomes, Centana"
    },
    {
        "id": "grp_002",
        "name": "HỘI MUA BÁN NHÀ ĐẤT SÀI GÒN - CHỢ BĐS 24/7",
        "group_url": "https://www.facebook.com/groups/nhadat.saigon.247",
        "category": "Toàn TP.HCM",
        "status": "active",
        "notes": "Nhóm đông thành viên, tương tác tốt"
    },
    {
        "id": "grp_003",
        "name": "CỘNG ĐỒNG CƯ DÂN & BĐS KHU ĐÔ THỊ PHÚ MỸ HƯNG QUẬN 7",
        "group_url": "https://www.facebook.com/groups/phumyhung.quan7.bds",
        "category": "Quận 7",
        "status": "active",
        "notes": "Nhóm tập trung phân khúc cao cấp"
    },
    {
        "id": "grp_004",
        "name": "NHÀ ĐẤT GÒ VẤP - BÌNH THẠNH - PHÚ NHUẬN",
        "group_url": "https://www.facebook.com/groups/nhadat.govap.binhthanh",
        "category": "Khu Tây Bắc",
        "status": "active",
        "notes": "Thích hợp nhà phố hẻm xe hơi"
    }
]


class GroupManager:
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or GROUPS_FILE
        self._groups: Dict[str, FBGroup] = {}
        self._load_groups()

    def _load_groups(self) -> None:
        if not self.storage_path.exists():
            self._groups = {}
            self._save_to_disk()
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._groups = {item["id"]: FBGroup(**item) for item in data}
        except Exception as exc:
            raise ValueError('Không đọc được danh sách nhóm; hãy kiểm tra file dữ liệu.') from exc

    def _save_to_disk(self) -> None:
        atomic_json(self.storage_path, [g.model_dump() for g in self._groups.values()])

    def list_groups(self, active_only: bool = False) -> List[FBGroup]:
        self._load_groups()
        groups = list(self._groups.values())
        if active_only:
            return [g for g in groups if g.status == "active"]
        return groups

    def get_group_by_id(self, group_id: str) -> Optional[FBGroup]:
        self._load_groups()
        return self._groups.get(group_id)

    def add_group(self, name: str, group_url: str, category: Optional[str] = None, notes: Optional[str] = None) -> FBGroup:
        with ExclusiveOperation(self.storage_path.with_suffix('.lock')):
            self._load_groups()
            return self._add_group(name, group_url, category, notes)

    def _add_group(self, name, group_url, category, notes):
        group_url = normalize_group_url(group_url)
        if not name.strip():
            raise InputError('Tên nhóm không được để trống.', 'name')
        if any(normalize_group_url(g.group_url) == group_url for g in self._groups.values()):
            raise InputError('Nhóm này đã có trong danh sách.', 'group_url', hint='Dùng nhóm đã lưu hoặc nhập đường dẫn của nhóm khác.')
        gid = f"grp_{uuid.uuid4().hex[:6]}"
        group = FBGroup(
            id=gid,
            name=name.strip(),
            group_url=group_url.strip(),
            category=category.strip() if category else "Chung",
            status="active",
            notes=notes
        )
        self._groups[gid] = group
        self._save_to_disk()
        return group

    def update_group(self, group_id: str, **kwargs) -> Optional[FBGroup]:
        with ExclusiveOperation(self.storage_path.with_suffix('.lock')):
            self._load_groups()
            return self._update_group(group_id, **kwargs)

    def _update_group(self, group_id, **kwargs):
        group = self._groups.get(group_id)
        if not group:
            return None
        data = group.model_dump()
        data.update(kwargs)
        data['group_url'] = normalize_group_url(data['group_url'])
        if any(g.id != group_id and normalize_group_url(g.group_url) == data['group_url'] for g in self._groups.values()):
            raise InputError('Nhóm này đã có trong danh sách.', 'group_url', hint='Dùng nhóm đã lưu hoặc nhập đường dẫn của nhóm khác.')
        updated = FBGroup(**data)
        self._groups[group_id] = updated
        self._save_to_disk()
        return updated

    def delete_group(self, group_id: str) -> bool:
        with ExclusiveOperation(self.storage_path.with_suffix('.lock')):
            self._load_groups()
            return self._delete_group(group_id)

    def _delete_group(self, group_id):
        if group_id in self._groups:
            del self._groups[group_id]
            self._save_to_disk()
            return True
        return False

    def import_groups_from_text(self, text: str) -> int:
        """Validate the entire import, then save once under a shared lock."""
        entries = []
        for line in text.splitlines():
            match = re.search(r'https?://(?:www\.|m\.)?facebook\.com/groups/[^\s]+', line.strip())
            if match:
                url = normalize_group_url(match.group(0))
                name = line.replace(match.group(0), '').strip() or 'Nhóm ' + url.rsplit('/', 1)[-1]
                entries.append((url, name))
        with ExclusiveOperation(self.storage_path.with_suffix('.lock')):
            self._load_groups()
            existing = {normalize_group_url(g.group_url) for g in self._groups.values()}
            added = 0
            for url, name in entries:
                if url in existing:
                    continue
                group = FBGroup(id='grp_' + uuid.uuid4().hex, name=name, group_url=url, category='Chung')
                self._groups[group.id] = group
                existing.add(url)
                added += 1
            self._save_to_disk()
            return added
