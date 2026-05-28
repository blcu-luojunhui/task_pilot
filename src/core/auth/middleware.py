from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from quart import Quart, request, jsonify
from quart.globals import request_ctx

from src.core.auth.context import current_account_id, current_account_role
from src.infra.database import AsyncMySQLPool

logger = logging.getLogger(__name__)

AUTH_WHITELIST = {
    "/api/health",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/metrics",
}


class AuthMiddleware:
    def __init__(self, app: Quart, db: AsyncMySQLPool):
        self._db = db
        self._app = app
        app.before_request(self._before_request)

    @staticmethod
    def _extract_token() -> str | None:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:]
        # EventSource 不支持自定义请求头，兜底从 query 参数取 token
        return request.args.get("token")

    @staticmethod
    def _is_static(path: str) -> bool:
        return not path.startswith("/api/")

    def _is_public_endpoint(self) -> bool:
        path = request.path
        if self._is_static(path):
            return True
        if path in AUTH_WHITELIST:
            return True
        # 检查 @public 装饰器
        if request.url_rule:
            view = self._app.view_functions.get(request.url_rule.endpoint)
            if view and getattr(view, "_auth_public", False):
                return True
        return False

    async def _before_request(self):
        if self._is_public_endpoint():
            return

        token = self._extract_token()
        if not token:
            return AuthMiddleware._abort(401, "缺少认证令牌")

        token_hash = hashlib.sha256(token.encode()).hexdigest()

        row = await self._db.async_fetch_one(
            "SELECT t.id AS token_id, t.account_id, t.token_prefix, t.expires_at, "
            "a.username, a.daily_token_limit, a.role "
            "FROM access_tokens t "
            "JOIN accounts a ON a.id = t.account_id "
            "WHERE t.token_hash = %s",
            params=(token_hash,),
        )

        if not row:
            return AuthMiddleware._abort(401, "无效的认证令牌")

        if row["expires_at"] and row["expires_at"] < _mysql_now():
            return AuthMiddleware._abort(401, "认证令牌已过期")

        current_account_id.set(row["account_id"])
        current_account_role.set(row.get("role", "user"))
        request_ctx.account_id = row["account_id"]
        request_ctx.account_role = row.get("role", "user")

        await self._db.async_save(
            "UPDATE access_tokens SET last_used_at = NOW() WHERE id = %s",
            (row["token_id"],),
        )

    @staticmethod
    def _abort(status: int, message: str):
        return jsonify({"code": status, "message": message, "data": None}), status


def _mysql_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
