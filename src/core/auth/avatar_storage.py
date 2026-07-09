from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

AvatarRole = Literal["user", "agent"]

_MAX_BYTES = 512 * 1024
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def avatars_root() -> Path:
    root = os.environ.get("TASK_PILOT_AVATAR_DIR")
    if root:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "avatars"


def _detect_mime(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def avatar_file_path(account_id: int, role: AvatarRole, ext: str) -> Path:
    return avatars_root() / str(account_id) / f"{role}{ext}"


def find_avatar_file(account_id: int, role: AvatarRole) -> Path | None:
    base = avatars_root() / str(account_id)
    if not base.is_dir():
        return None
    for ext in _ALLOWED_MIME.values():
        candidate = base / f"{role}{ext}"
        if candidate.is_file():
            return candidate
    return None


def validate_filename(filename: str | None) -> None:
    if not filename or not filename.strip():
        raise ValueError("无效的文件名")
    name = filename.strip().split("/")[-1].split("\\")[-1]
    if ".." in name or name.startswith("."):
        raise ValueError("无效的文件名")
    dot = name.rfind(".")
    if dot <= 0:
        raise ValueError("文件缺少扩展名")
    ext = name[dot:].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 JPEG / PNG / WebP / GIF")


def avatar_version_key(role: AvatarRole, account: dict) -> str | None:
    return account.get("avatar_url") if role == "user" else account.get("agent_avatar_url")


def validate_avatar_bytes(data: bytes, content_type: str | None) -> tuple[str, str]:
    if len(data) > _MAX_BYTES:
        raise ValueError("图片大小不能超过 512KB")
    if len(data) < 16:
        raise ValueError("无效的图片文件")

    detected = _detect_mime(data)
    if not detected:
        raise ValueError("仅支持 JPEG / PNG / WebP / GIF")

    if content_type and content_type.split(";")[0].strip() in _ALLOWED_MIME:
        if content_type.split(";")[0].strip() != detected:
            # 以魔数为准，忽略不一致的 Content-Type
            pass

    ext = _ALLOWED_MIME[detected]
    return detected, ext


def save_avatar(
    account_id: int,
    role: AvatarRole,
    data: bytes,
    content_type: str | None,
    *,
    filename: str | None = None,
) -> str:
    if filename:
        validate_filename(filename)
    _mime, ext = validate_avatar_bytes(data, content_type)
    base = avatars_root() / str(account_id)
    base.mkdir(parents=True, exist_ok=True)

    # 清除同角色旧扩展名
    for old_ext in _ALLOWED_MIME.values():
        old = base / f"{role}{old_ext}"
        if old.is_file() and old_ext != ext:
            old.unlink(missing_ok=True)

    target = base / f"{role}{ext}"
    target.write_bytes(data)

    import time
    return str(int(time.time() * 1000))


def delete_avatar(account_id: int, role: AvatarRole) -> None:
    path = find_avatar_file(account_id, role)
    if path and path.is_file():
        path.unlink(missing_ok=True)
    base = avatars_root() / str(account_id)
    if base.is_dir() and not any(base.iterdir()):
        base.rmdir()


def mime_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    for mime, suffix in _ALLOWED_MIME.items():
        if suffix == ext:
            return mime
    return "application/octet-stream"


_ROLE_RE = re.compile(r"^(user|agent)$")


def parse_avatar_role(raw: str) -> AvatarRole:
    if _ROLE_RE.match(raw):
        return raw  # type: ignore[return-value]
    raise ValueError("role 必须为 user 或 agent")
