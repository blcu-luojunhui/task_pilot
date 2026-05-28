from __future__ import annotations

from functools import wraps
from typing import Callable


def public(fn: Callable) -> Callable:
    """标记端点无需鉴权，AuthMiddleware 自动放行。"""
    setattr(fn, "_auth_public", True)
    return fn


def require_role(role: str) -> Callable:
    """标记端点需要特定角色（配合 AuthMiddleware 使用）。"""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)
        setattr(wrapper, "_auth_required_role", role)
        return wrapper
    return decorator
