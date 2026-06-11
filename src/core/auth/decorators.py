from __future__ import annotations

from functools import wraps
from typing import Callable

from quart import jsonify

from src.core.auth.context import current_account_role


def public(fn: Callable) -> Callable:
    """标记端点无需鉴权，AuthMiddleware 自动放行。"""
    setattr(fn, "_auth_public", True)
    return fn


def require_role(role: str) -> Callable:
    """标记端点需要特定角色，不匹配返回 403。"""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            current = current_account_role.get()
            if current != role:
                return jsonify({"code": 403, "message": "权限不足", "data": None}), 403
            return await fn(*args, **kwargs)
        return wrapper
    return decorator
