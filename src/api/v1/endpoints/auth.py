from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, date
from typing import Any

from pydantic import BaseModel, Field
from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies
from src.core.auth import get_current_account_id, DuplicateError, UnauthorizedError
from src.core.auth.context import current_account_id
from src.infra.shared.error_codes import ErrorCode

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    revoke_others: bool = Field(default=False, description="是否吊销该账号其他所有 Token")


class CreateTokenRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class ChangeEmailRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=128)


class _JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def _ok(data: Any, message: str = "success") -> tuple:
    body = json.dumps(
        {"code": ErrorCode.SUCCESS, "message": message, "data": data},
        cls=_JsonEncoder,
        ensure_ascii=False,
    )
    return body, 200, {"Content-Type": "application/json"}


def _error(code: int, message: str, status: int) -> tuple:
    body = json.dumps(
        {"code": code, "message": message, "data": None},
        ensure_ascii=False,
    )
    return body, status, {"Content-Type": "application/json"}


def create_auth_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("auth", __name__)

    @bp.route("/auth/register", methods=["POST"])
    async def register():
        try:
            body = RegisterRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            result = await deps.auth.register(body.username, body.email, body.password)
        except DuplicateError as e:
            return _error(ErrorCode.BAD_REQUEST, str(e), 409)
        except Exception as e:
            logger.exception("注册失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "注册失败", 500)

        return _ok(result, "注册成功")

    @bp.route("/auth/login", methods=["POST"])
    async def login():
        try:
            body = LoginRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            result = await deps.auth.login(body.username, body.password, body.revoke_others)
        except UnauthorizedError as e:
            return _error(ErrorCode.UNAUTHORIZED, str(e), 401)
        except Exception as e:
            logger.exception("登录失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "登录失败", 500)

        return _ok(result, "登录成功")

    @bp.route("/auth/refresh", methods=["POST"])
    async def refresh():
        try:
            body = RefreshRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            result = await deps.auth.refresh_access_token(body.refresh_token)
        except UnauthorizedError as e:
            return _error(ErrorCode.UNAUTHORIZED, str(e), 401)
        except Exception as e:
            logger.exception("刷新 Token 失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "刷新 Token 失败", 500)

        return _ok(result, "Token 已刷新")

    @bp.route("/auth/logout", methods=["POST"])
    async def logout():
        token = _extract_bearer()
        if not token:
            return _error(ErrorCode.UNAUTHORIZED, "缺少认证令牌", 401)

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await deps.auth.revoke_current_token(token_hash)
        current_account_id.set(None)
        return _ok(None, "已登出")

    @bp.route("/auth/me", methods=["GET"])
    async def me():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        account = await deps.auth.get_account_info(account_id)
        if not account:
            return _error(ErrorCode.UNAUTHORIZED, "账号不存在", 404)

        # 不泄露密码哈希和盐
        account.pop("password_hash", None)
        account.pop("password_salt", None)
        return _ok(account)

    @bp.route("/auth/password", methods=["PUT"])
    async def change_password():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        try:
            body = ChangePasswordRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            await deps.auth.change_password(account_id, body.old_password, body.new_password)
        except UnauthorizedError as e:
            return _error(ErrorCode.UNAUTHORIZED, str(e), 401)
        except Exception as e:
            logger.exception("修改密码失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "修改密码失败", 500)

        return _ok(None, "密码已修改")

    @bp.route("/auth/email", methods=["PUT"])
    async def change_email():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        try:
            body = ChangeEmailRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            await deps.auth.change_email(account_id, body.email)
        except DuplicateError as e:
            return _error(ErrorCode.BAD_REQUEST, str(e), 409)
        except Exception as e:
            logger.exception("修改邮箱失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "修改邮箱失败", 500)

        return _ok(None, "邮箱已修改")

    @bp.route("/auth/account", methods=["DELETE"])
    async def delete_account():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        try:
            await deps.auth.delete_account(account_id)
        except Exception as e:
            logger.exception("注销账号失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "注销账号失败", 500)

        current_account_id.set(None)
        return _ok(None, "账号已注销")

    @bp.route("/auth/tokens", methods=["POST"])
    async def create_token():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        try:
            body = CreateTokenRequest.model_validate(await request.get_json())
        except Exception:
            body = CreateTokenRequest()

        result = await deps.auth.create_token(account_id, body.name)
        return _ok(result, "令牌创建成功")

    @bp.route("/auth/tokens", methods=["GET"])
    async def list_tokens():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        tokens = await deps.auth.list_tokens(account_id)
        return _ok(tokens)

    @bp.route("/auth/tokens/<int:token_id>", methods=["DELETE"])
    async def revoke_token(token_id: int):
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        success = await deps.auth.revoke_token(token_id, account_id)
        if not success:
            return _error(ErrorCode.BAD_REQUEST, "令牌不存在", 404)

        return _ok(None, "已吊销")

    return bp


def _extract_bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None
