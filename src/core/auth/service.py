from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.auth.token import (
    generate_token,
    hash_password,
    verify_password_with_legacy,
)
from src.core.auth.repository import (
    AccountRepository,
    TokenRepository,
    UsageRepository,
    InviteCodeRepository,
    LoginFailureRepository,
)
from src.core.config.auth_config import AuthConfig
from src.infra.database import AsyncMySQLPool


class AuthService:
    def __init__(self, db: AsyncMySQLPool, config: AuthConfig):
        self._db = db
        self._config = config
        self.accounts = AccountRepository(db)
        self.tokens = TokenRepository(db)
        self.usage = UsageRepository(db)
        self.invite_codes = InviteCodeRepository(db)
        self.login_failures = LoginFailureRepository(db)

    # ── 注册 / 登录 ──────────────────────────────────────────────

    async def register(
        self, username: str, email: str, password: str, invite_code: Optional[str] = None
    ) -> dict:
        if self._config.registration_require_invite:
            if not invite_code:
                raise DuplicateError("注册失败，请检查输入或联系管理员")
            reserved = await self.invite_codes.reserve(invite_code)
            if not reserved:
                raise DuplicateError("注册失败，请检查输入或联系管理员")

        allowed = [d.strip() for d in self._config.allowed_email_domains.split(",") if d.strip()]
        domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
        if domain not in allowed:
            raise DuplicateError("注册失败，请检查输入或联系管理员")

        try:
            existing = await self.accounts.find_by_username(username)
            if existing:
                raise DuplicateError("注册失败，请检查输入或联系管理员")
            existing = await self.accounts.find_by_email(email)
            if existing:
                raise DuplicateError("注册失败，请检查输入或联系管理员")

            pw_hash = hash_password(password)
            account_id = await self.accounts.create(
                username=username,
                email=email,
                password_hash=pw_hash,
                daily_limit=self._config.default_daily_token_limit,
            )

            if invite_code:
                await self.invite_codes.assign(invite_code, account_id)

            return await self._issue_tokens(account_id, username)
        except Exception:
            if invite_code:
                await self.invite_codes.release(invite_code)
            raise

    async def login(
        self, username: str, password: str, revoke_others: bool = False
    ) -> dict:
        account = await self.accounts.find_by_username(username)
        if not account:
            raise UnauthorizedError("用户名或密码错误")

        account_id = account["id"]

        locked, remaining = await self.login_failures.check_locked(account_id)
        if locked:
            minutes = max(1, remaining // 60)
            raise LockedError(
                f"账户已锁定，请 {minutes} 分钟后重试", remaining
            )

        ok, new_hash = verify_password_with_legacy(
            password, account["password_hash"], account.get("password_salt", "")
        )
        if not ok:
            await self.login_failures.record_failure(account_id, "")
            row = await self._db.async_fetch_one(
                "SELECT fail_count FROM account_login_failures WHERE account_id = %s",
                params=(account_id,),
            )
            if row and row["fail_count"] >= self._config.login_max_failures:
                await self.login_failures.lock_account(account_id, self._config.login_lock_minutes)
                raise LockedError(
                    f"密码错误次数过多，账户已锁定 {self._config.login_lock_minutes} 分钟",
                    self._config.login_lock_minutes * 60,
                )
            raise UnauthorizedError("用户名或密码错误")

        await self.login_failures.reset_failures(account_id)

        if new_hash:
            await self.accounts.update_password_hash(account_id, new_hash)

        if revoke_others:
            await self.tokens.revoke_all_for_account(account_id)
            await self._db.async_save(
                "DELETE FROM refresh_tokens WHERE account_id = %s", (account_id,)
            )

        return await self._issue_tokens(account_id, account["username"])

    # ── 邀请码管理 ──────────────────────────────────────────────

    async def create_invite_codes(
        self, admin_id: int, *, count: int = 0, codes: list[str] | None = None
    ) -> list[str]:
        """生成邀请码。codes 非空时使用手动指定的码，否则按 count 随机生成。"""
        if codes:
            if len(codes) > 100:
                raise ValueError("单次手动输入最多 100 个")
            for c in codes:
                if not c.strip() or len(c) > 32:
                    raise ValueError(f"邀请码无效: {c}")
            return await self.invite_codes.create_batch(admin_id, codes)
        else:
            if count < 1 or count > 100:
                raise ValueError("单次随机生成数量需在 1-100 之间")
            generated = [_random_code() for _ in range(count)]
            return await self.invite_codes.create_batch(admin_id, generated)

    async def list_invite_codes(self, page: int = 1, page_size: int = 20) -> dict:
        rows, total = await self.invite_codes.list_all(page, page_size)
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    # ── Token 管理 ──────────────────────────────────────────────

    async def create_token(self, account_id: int, name: Optional[str] = None) -> dict:
        raw_token, token_hash, token_prefix = generate_token(self._config.token_prefix)
        expires_at = self._compute_expires_at()
        await self.tokens.create(account_id, token_hash, token_prefix, name, expires_at)
        return {
            "token": raw_token,
            "token_prefix": token_prefix,
            "name": name,
            "expires_at": expires_at,
        }

    async def list_tokens(self, account_id: int) -> list[dict]:
        return await self.tokens.list_by_account(account_id)

    async def revoke_token(self, token_id: int, account_id: int) -> bool:
        return await self.tokens.delete(token_id, account_id)

    async def revoke_current_token(self, token_hash: str) -> None:
        await self._db.async_save(
            "DELETE FROM access_tokens WHERE token_hash = %s", (token_hash,)
        )

    async def revoke_other_tokens(self, account_id: int, exclude_hash: str) -> int:
        affected = await self._db.async_save(
            "DELETE FROM access_tokens WHERE account_id = %s AND token_hash != %s",
            (account_id, exclude_hash),
        )
        return affected

    # ── Refresh Token ─────────────────────────────────────────

    async def refresh_access_token(self, refresh_token: str) -> dict:
        import hashlib
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()

        row = await self._db.async_fetch_one(
            "SELECT r.id, r.account_id, r.token_prefix, r.expires_at, "
            "a.username "
            "FROM refresh_tokens r "
            "JOIN accounts a ON a.id = r.account_id "
            "WHERE r.token_hash = %s",
            params=(token_hash,),
        )

        if not row:
            raise UnauthorizedError("无效的 Refresh Token")

        if row["expires_at"] and row["expires_at"] < _mysql_now():
            raise UnauthorizedError("Refresh Token 已过期")

        await self._db.async_save(
            "DELETE FROM refresh_tokens WHERE id = %s", (row["id"],)
        )

        return await self._issue_tokens(row["account_id"], row["username"])

    # ── 账号信息 ──────────────────────────────────────────────────

    async def get_account_info(self, account_id: int) -> Optional[dict]:
        account = await self.accounts.find_by_id(account_id)
        if not account:
            return None
        usage = await self.usage.get_today_usage(account_id)
        account["today_tokens_used"] = usage["tokens_used"]
        account["role"] = account.get("role", "user")
        return account

    async def list_users(self, page: int = 1, page_size: int = 20) -> dict:
        rows, total = await self.accounts.list_all(page, page_size)
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    async def update_user_role(self, account_id: int, role: str) -> bool:
        if role not in ("admin", "user"):
            raise ValueError(f"Invalid role: {role}")
        return await self.accounts.update_role(account_id, role)

    async def update_user_quota(self, account_id: int, limit: int) -> bool:
        if limit < 0:
            raise ValueError("配额不能为负数")
        return await self.accounts.update_daily_limit(account_id, limit)

    # ── Admin: 任务管理 ────────────────────────────────────────

    async def list_all_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: list[int] | None = None,
        task_name: str | None = None,
        date: str | None = None,
        trace_id_q: str | None = None,
    ) -> dict:
        conditions: list[str] = ["1=1"]
        params: list = []

        if status_filter:
            placeholders = ",".join(["%s"] * len(status_filter))
            conditions.append(f"task_status IN ({placeholders})")
            params.extend(status_filter)

        if task_name:
            escaped = "%" + task_name.replace("%", r"\%").replace("_", r"\_") + "%"
            conditions.append("task_name LIKE %s")
            params.append(escaped)

        if date:
            conditions.append("date_string = %s")
            params.append(date)

        if trace_id_q:
            escaped = "%" + trace_id_q.replace("%", r"\%").replace("_", r"\_") + "%"
            conditions.append("trace_id LIKE %s")
            params.append(escaped)

        where = "WHERE " + " AND ".join(conditions)
        total_row = await self._db.async_fetch_one(
            f"SELECT COUNT(*) AS c FROM task_manager {where}", params=tuple(params)
        )
        total = total_row["c"] if total_row else 0
        rows = await self._db.async_fetch(
            f"SELECT * FROM task_manager {where} ORDER BY start_timestamp DESC LIMIT %s OFFSET %s",
            params=(*params, page_size, (page - 1) * page_size),
        )
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    async def cancel_any_task(self, trace_id: str) -> bool:
        affected = await self._db.async_save(
            "UPDATE task_manager SET task_status = 4 WHERE trace_id = %s "
            "AND task_status IN (0, 1)",
            (trace_id,),
        )
        return affected > 0

    # ── Admin: 用量排名 ────────────────────────────────────────

    async def get_usage_ranking(self, days: int = 7) -> list[dict]:
        rows = await self._db.async_fetch(
            "SELECT a.username, a.role, SUM(du.tokens_used) AS total_tokens "
            "FROM account_daily_usage du "
            "JOIN accounts a ON a.id = du.account_id "
            "WHERE du.usage_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
            "GROUP BY du.account_id "
            "ORDER BY total_tokens DESC",
            params=(days,),
        )
        return rows

    # ── 账号管理 ──────────────────────────────────────────────────

    async def change_password(self, account_id: int, old_password: str, new_password: str) -> None:
        account = await self.accounts.find_by_id(account_id)
        if not account:
            raise UnauthorizedError("账号不存在")

        ok, new_hash = verify_password_with_legacy(
            old_password, account["password_hash"], account.get("password_salt", "")
        )
        if not ok:
            raise UnauthorizedError("原密码错误")

        await self.accounts.update_password_hash(account_id, hash_password(new_password))

    async def change_email(self, account_id: int, new_email: str) -> None:
        existing = await self.accounts.find_by_email(new_email)
        if existing and existing["id"] != account_id:
            raise DuplicateError("邮箱已被其他账号使用")
        await self.accounts.update_email(account_id, new_email)

    async def delete_account(self, account_id: int) -> None:
        from src.core.auth.avatar_storage import delete_avatar

        delete_avatar(account_id, "user")
        delete_avatar(account_id, "agent")
        await self.accounts.delete(account_id)

    async def upload_avatar(
        self, account_id: int, role: str, data: bytes, content_type: str | None, *, filename: str | None = None
    ) -> dict:
        from src.core.auth.avatar_storage import parse_avatar_role, save_avatar

        parsed_role = parse_avatar_role(role)
        version_key = save_avatar(
            account_id, parsed_role, data, content_type, filename=filename
        )
        await self.accounts.update_avatar_url(account_id, parsed_role, version_key)
        account = await self.get_account_info(account_id)
        if not account:
            raise UnauthorizedError("账号不存在")
        return account

    async def remove_avatar(self, account_id: int, role: str) -> dict:
        from src.core.auth.avatar_storage import delete_avatar, parse_avatar_role

        parsed_role = parse_avatar_role(role)
        delete_avatar(account_id, parsed_role)
        await self.accounts.update_avatar_url(account_id, parsed_role, None)
        account = await self.get_account_info(account_id)
        if not account:
            raise UnauthorizedError("账号不存在")
        return account

    async def get_avatar_file(self, account_id: int, role: str):
        from src.core.auth.avatar_storage import (
            avatar_version_key,
            find_avatar_file,
            mime_for_path,
            parse_avatar_role,
        )

        parsed_role = parse_avatar_role(role)
        account = await self.accounts.find_by_id(account_id)
        if not account:
            return None, None, None

        version_key = avatar_version_key(parsed_role, account)
        if not version_key:
            return None, None, None

        path = find_avatar_file(account_id, parsed_role)
        if not path:
            await self.accounts.update_avatar_url(account_id, parsed_role, None)
            return None, None, None

        return path, mime_for_path(path), version_key

    # ── Token 用量 ─────────────────────────────────────────────

    async def check_quota(self, account_id: int) -> tuple[bool, int, int]:
        return await self.usage.check_limit(account_id)

    async def record_usage(self, account_id: int, tokens: int) -> None:
        if tokens > 0:
            await self.usage.increment_usage(account_id, tokens)

    # ── 内部方法 ──────────────────────────────────────────────────

    async def _issue_tokens(self, account_id: int, username: str) -> dict:
        raw_token, token_hash, token_prefix = generate_token(self._config.token_prefix)
        expires_at = self._compute_expires_at()
        access_id = await self.tokens.create(account_id, token_hash, token_prefix, None, expires_at)

        rt_raw, rt_hash, rt_prefix = generate_token(self._config.refresh_token_prefix)
        rt_expires = self._compute_refresh_expires_at()
        await self._db.async_save(
            "INSERT INTO refresh_tokens (account_id, token_hash, token_prefix, access_token_id, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (account_id, rt_hash, rt_prefix, access_id, rt_expires),
        )

        return {
            "account_id": account_id,
            "username": username,
            "token": raw_token,
            "token_prefix": token_prefix,
            "expires_at": expires_at,
            "refresh_token": rt_raw,
            "refresh_token_prefix": rt_prefix,
            "refresh_token_expires_at": rt_expires,
        }

    def _compute_expires_at(self) -> Optional[str]:
        expire_days = self._config.token_expire_days
        if expire_days <= 0:
            return None
        expire_date = datetime.now(timezone.utc) + timedelta(days=expire_days)
        return expire_date.strftime("%Y-%m-%d %H:%M:%S")

    def _compute_refresh_expires_at(self) -> Optional[str]:
        expire_days = self._config.refresh_token_expire_days
        if expire_days <= 0:
            return None
        expire_date = datetime.now(timezone.utc) + timedelta(days=expire_days)
        return expire_date.strftime("%Y-%m-%d %H:%M:%S")


class DuplicateError(Exception):
    pass


class UnauthorizedError(Exception):
    pass


class LockedError(Exception):
    def __init__(self, message: str, remaining_seconds: int = 0):
        super().__init__(message)
        self.remaining_seconds = remaining_seconds


def _mysql_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


_ALPHABET = string.ascii_uppercase + string.digits  # 去掉易混淆字符
_ALPHABET = _ALPHABET.translate(str.maketrans("", "", "0O1IL"))


def _random_code(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
