from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, date
from typing import Any

from pydantic import BaseModel, Field
from quart import Blueprint, request

from src.api.v1.utils import ApiDependencies
from src.core.auth import get_current_account_id, DuplicateError, UnauthorizedError, LockedError
from src.core.auth.context import current_account_id
from src.core.auth.decorators import require_role
from src.api.v1.utils.json_columns import decode_json_columns
from src.infra.shared.error_codes import ErrorCode

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    email: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=6, max_length=128)
    invite_code: str | None = Field(default=None, description="邀请码")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    revoke_others: bool = Field(default=False, description="是否吊销该账号其他所有 Token")


class CreateTokenRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)


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
            result = await deps.auth.register(
                body.username, body.email, body.password, body.invite_code
            )
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
        except LockedError as e:
            return _error(ErrorCode.LOGIN_LOCKED, str(e), 423)
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

    @bp.route("/auth/avatar", methods=["POST"])
    async def upload_avatar():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        role = request.args.get("role", "user")
        try:
            from src.core.auth.avatar_storage import parse_avatar_role

            parse_avatar_role(role)
        except ValueError as e:
            return _error(ErrorCode.VALIDATION_ERROR, str(e), 400)

        files = await request.files
        upload = files.get("file")
        if not upload or not upload.filename:
            return _error(ErrorCode.VALIDATION_ERROR, "请上传图片文件", 400)

        data = upload.read()
        if not data:
            return _error(ErrorCode.VALIDATION_ERROR, "空文件", 400)

        try:
            account = await deps.auth.upload_avatar(
                account_id,
                role,
                data,
                upload.content_type,
                filename=upload.filename,
            )
        except ValueError as e:
            return _error(ErrorCode.VALIDATION_ERROR, str(e), 400)
        except Exception as e:
            logger.exception("上传头像失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "上传头像失败", 500)

        account.pop("password_hash", None)
        account.pop("password_salt", None)
        return _ok(account, "头像已更新")

    @bp.route("/auth/avatar", methods=["DELETE"])
    async def delete_avatar():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        role = request.args.get("role", "user")
        try:
            account = await deps.auth.remove_avatar(account_id, role)
        except ValueError as e:
            return _error(ErrorCode.VALIDATION_ERROR, str(e), 400)
        except Exception as e:
            logger.exception("删除头像失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "删除头像失败", 500)

        account.pop("password_hash", None)
        account.pop("password_salt", None)
        return _ok(account, "头像已删除")

    @bp.route("/auth/avatar/image", methods=["GET"])
    async def get_avatar_image():
        account_id = get_current_account_id()
        if not account_id:
            return _error(ErrorCode.UNAUTHORIZED, "未登录", 401)

        role = request.args.get("role", "user")
        try:
            path, mime, version_key = await deps.auth.get_avatar_file(account_id, role)
        except ValueError as e:
            return _error(ErrorCode.VALIDATION_ERROR, str(e), 400)

        if not path or not mime:
            return _error(ErrorCode.BAD_REQUEST, "头像不存在", 404)

        from quart import send_file

        cache_version = request.args.get("v") or version_key
        response = await send_file(
            path,
            mimetype=mime,
            cache_timeout=86_400,
            conditional=True,
            add_etags=False,
        )
        if cache_version:
            response.set_etag(cache_version)
        response.cache_control.public = False
        response.cache_control.private = True
        return response

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

    # ── Admin 端点 ───────────────────────────────────────────

    class UpdateRoleRequest(BaseModel):
        role: str = Field(..., pattern=r"^(admin|user)$")

    @bp.route("/auth/admin/users", methods=["GET"])
    @require_role("admin")
    async def admin_list_users():
        try:
            page = max(int(request.args.get("page", 1)), 1)
            page_size = min(int(request.args.get("page_size", 20)), 100)
        except (TypeError, ValueError):
            page, page_size = 1, 20

        result = await deps.auth.list_users(page, page_size)
        return _ok(result)

    @bp.route("/auth/admin/users/<int:user_id>/role", methods=["PUT"])
    @require_role("admin")
    async def admin_update_user_role(user_id: int):
        try:
            body = UpdateRoleRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        account_id = get_current_account_id()
        if user_id == account_id:
            return _error(ErrorCode.BAD_REQUEST, "不能修改自己的角色", 400)

        try:
            updated = await deps.auth.update_user_role(user_id, body.role)
        except ValueError as e:
            return _error(ErrorCode.BAD_REQUEST, str(e), 400)
        except Exception as e:
            logger.exception("更新用户角色失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "更新角色失败", 500)

        if not updated:
            return _error(ErrorCode.BAD_REQUEST, "用户不存在", 404)

        return _ok(None, f"角色已更新为 {body.role}")

    class UpdateQuotaRequest(BaseModel):
        daily_token_limit: int = Field(..., ge=0)

    @bp.route("/auth/admin/users/<int:user_id>/quota", methods=["PUT"])
    @require_role("admin")
    async def admin_update_user_quota(user_id: int):
        try:
            body = UpdateQuotaRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请求参数校验失败", 400)

        try:
            updated = await deps.auth.update_user_quota(user_id, body.daily_token_limit)
        except ValueError as e:
            return _error(ErrorCode.BAD_REQUEST, str(e), 400)
        except Exception as e:
            logger.exception("更新用户配额失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "更新配额失败", 500)

        if not updated:
            return _error(ErrorCode.BAD_REQUEST, "用户不存在", 404)

        return _ok(None, "配额已更新")

    # ── Admin: 邀请码管理 ─────────────────────────────────────

    class CreateInviteCodesRequest(BaseModel):
        count: int = Field(default=0, ge=0, le=100)
        codes: list[str] | None = Field(default=None, description="手动指定邀请码列表")

    @bp.route("/auth/admin/invite-codes", methods=["POST"])
    @require_role("admin")
    async def admin_create_invite_codes():
        try:
            body = CreateInviteCodesRequest.model_validate(await request.get_json())
        except Exception:
            return _error(ErrorCode.VALIDATION_ERROR, "请提供 count (1-100) 或 codes 列表", 400)

        if not body.codes and body.count < 1:
            return _error(ErrorCode.VALIDATION_ERROR, "请提供 count (1-100) 或 codes 列表", 400)

        account_id = get_current_account_id()
        try:
            codes = await deps.auth.create_invite_codes(
                account_id, count=body.count, codes=body.codes
            )
        except ValueError as e:
            return _error(ErrorCode.BAD_REQUEST, str(e), 400)
        except Exception as e:
            logger.exception("生成邀请码失败: %s", e)
            return _error(ErrorCode.INTERNAL_ERROR, "生成邀请码失败", 500)

        return _ok({"codes": codes, "count": len(codes)}, "已生成")

    @bp.route("/auth/admin/invite-codes", methods=["GET"])
    @require_role("admin")
    async def admin_list_invite_codes():
        try:
            page = max(int(request.args.get("page", 1)), 1)
            page_size = min(int(request.args.get("page_size", 20)), 100)
        except (TypeError, ValueError):
            page, page_size = 1, 20

        result = await deps.auth.list_invite_codes(page, page_size)
        return _ok(result)

    # ── Admin: 任务管理 ──────────────────────────────────────

    @bp.route("/auth/admin/tasks", methods=["GET"])
    @require_role("admin")
    async def admin_list_tasks():
        try:
            page = max(int(request.args.get("page", 1)), 1)
            page_size = min(int(request.args.get("page_size", 20)), 100)
        except (TypeError, ValueError):
            page, page_size = 1, 20

        status_filter = None
        raw_status = request.args.getlist("status")
        if raw_status:
            try:
                status_filter = [int(s) for s in raw_status]
            except (TypeError, ValueError):
                pass

        task_name = request.args.get("task_name")
        date = request.args.get("date")
        trace_id_q = request.args.get("trace_id")

        result = await deps.auth.list_all_tasks(
            page, page_size, status_filter, task_name, date, trace_id_q
        )
        items = decode_json_columns(result["items"], ["data"], default={})
        result["items"] = items
        return _ok(result)

    @bp.route("/auth/admin/tasks/<trace_id>/cancel", methods=["POST"])
    @require_role("admin")
    async def admin_cancel_task(trace_id: str):
        cancelled = await deps.auth.cancel_any_task(trace_id)
        if not cancelled:
            return _error(ErrorCode.BAD_REQUEST, "任务不存在或状态不允许取消", 404)
        return _ok(None, "已请求取消")

    # ── Admin: 用量排名 ──────────────────────────────────────

    @bp.route("/auth/admin/stats/usage", methods=["GET"])
    @require_role("admin")
    async def admin_usage_ranking():
        try:
            days = max(min(int(request.args.get("days", 7)), 90), 1)
        except (TypeError, ValueError):
            days = 7

        ranking = await deps.auth.get_usage_ranking(days)
        return _ok({"days": days, "ranking": ranking})

    return bp


def _extract_bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None
