from __future__ import annotations

import hashlib
import secrets

import bcrypt

_BCRYPT_PREFIX = "$2b$"


def generate_token(prefix: str = "sk-") -> tuple[str, str, str]:
    raw = prefix + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_prefix = raw[: len(prefix) + 8]
    return raw, token_hash, token_prefix


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(_BCRYPT_PREFIX):
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    # 兼容旧版 SHA-256 哈希，验密后上游负责升级为 bcrypt
    return _verify_legacy_sha256(password, stored_hash)


def verify_password_with_legacy(password: str, stored_hash: str, salt: str) -> tuple[bool, str | None]:
    """验密，如果是旧 SHA-256 格式则返回新 bcrypt hash 供升级。"""
    if stored_hash.startswith(_BCRYPT_PREFIX):
        return bcrypt.checkpw(password.encode(), stored_hash.encode()), None
    if _verify_legacy_sha256(password, stored_hash, salt):
        return True, hash_password(password)
    return False, None


def _verify_legacy_sha256(password: str, stored_hash: str, salt: str = "") -> bool:
    return hashlib.sha256((password + salt).encode()).hexdigest() == stored_hash


def generate_salt() -> str:
    """已废弃：bcrypt 内置盐，保留此函数仅用于兼容旧代码。"""
    return secrets.token_hex(16)
