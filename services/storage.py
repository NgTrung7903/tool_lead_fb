"""Atomic local storage and cross-process locks. Never hide corrupt data."""
import json
import os
import tempfile
from pathlib import Path

from filelock import FileLock, Timeout


class ResourceBusyError(RuntimeError):
    pass


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ExclusiveOperation:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # The API reserves a run before handing ownership to its worker thread.
        self.lock = FileLock(str(path), thread_local=False)

    def __enter__(self):
        try:
            self.lock.acquire(timeout=0)
        except Timeout as exc:
            raise ResourceBusyError('Đang có thao tác khác sử dụng phiên trình duyệt. Hãy đợi hoàn tất.') from exc
        return self

    def __exit__(self, *args):
        self.lock.release()
