import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

# ==================== 路径定位 ====================


def _app_data_dir() -> Path:
    """定位 %APPDATA%/<AppName>/ 目录（跨平台由 Qt 处理）。"""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    p = Path(base) if base else Path.home() / ".deepseek_desktop"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sessions_root() -> Path:
    p = _app_data_dir() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _session_dir(session_id: str) -> Path:
    return _sessions_root() / session_id


def _meta_file(session_id: str) -> Path:
    return _session_dir(session_id) / "meta.json"


def _messages_file(session_id: str) -> Path:
    return _session_dir(session_id) / "messages.json"


def _images_dir(session_id: str) -> Path:
    p = _session_dir(session_id) / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 会话管理 ====================


def list_sessions() -> list[dict]:
    """
    返回所有会话元数据，按 updated_at 降序排列。
    每项: {"id", "name", "size_bytes", "created_at", "updated_at"}
    """
    root = _sessions_root()
    if not root.exists():
        return []
    sessions = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sessions.append(
            {
                "id": d.name,
                "name": meta.get("name", "未命名会话"),
                "size_bytes": _dir_size(d),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
            }
        )
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


def create_session(name: str) -> str:
    """创建新会话目录，返回 session_id。"""
    sid = uuid.uuid4().hex
    d = _session_dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    meta = {"name": name.strip() or "未命名会话", "created_at": now, "updated_at": now}
    _meta_file(sid).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _messages_file(sid).write_text("[]", encoding="utf-8")
    _images_dir(sid)
    return sid


def delete_session(session_id: str) -> None:
    """递归删除整个会话目录。"""
    d = _session_dir(session_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def get_session_name(session_id: str) -> str:
    try:
        meta = json.loads(_meta_file(session_id).read_text(encoding="utf-8"))
        return meta.get("name", "未命名会话")
    except (json.JSONDecodeError, OSError):
        return "未命名会话"


# ==================== 消息 ====================


def load_messages(session_id: str) -> list[dict]:
    path = _messages_file(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_messages(session_id: str, messages: list[dict]) -> None:
    """原子写入消息，同时刷新 meta.json 的 updated_at。"""
    path = _messages_file(session_id)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)
    except OSError:
        return

    meta_path = _meta_file(session_id)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        meta = {
            "name": "未命名会话",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    meta_tmp = meta_path.with_suffix(".meta.tmp")
    try:
        meta_tmp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        meta_tmp.replace(meta_path)
    except OSError:
        pass


def clear_session_messages(session_id: str) -> None:
    """清空当前会话的消息和图片，但保留会话本身。"""
    try:
        _messages_file(session_id).write_text("[]", encoding="utf-8")
    except OSError:
        pass
    try:
        for p in _images_dir(session_id).iterdir():
            try:
                if p.is_file():
                    p.unlink()
            except OSError:
                pass
    except OSError:
        pass


# ==================== 图片 ====================


def save_image(session_id: str, raw_bytes: bytes, suffix: str) -> str | None:
    try:
        ext = suffix.lstrip(".").lower() or "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        (_images_dir(session_id) / filename).write_bytes(raw_bytes)
        return filename
    except OSError:
        return None


def image_abs_path(session_id: str, rel_name: str) -> Path:
    return _images_dir(session_id) / rel_name


# ==================== 工具函数 ====================


def _dir_size(d: Path) -> int:
    total = 0
    try:
        for p in d.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def format_size(num_bytes: int) -> str:
    """人类可读的文件大小。"""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / 1024 / 1024:.2f} MB"
    return f"{num_bytes / 1024 / 1024 / 1024:.2f} GB"
