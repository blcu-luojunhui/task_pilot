from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.core.auth.token import (
    generate_token,
    hash_password,
    verify_password_with_legacy,
)
from src.core.auth.repository import AccountRepository, TokenRepository, UsageRepository
from src.core.config.auth_config import AuthConfig
from src.infra.database import AsyncMySQLPool


class AuthService:
    def __init__(self, db: AsyncMySQLPool, config: AuthConfig):
        self._db = db
        self._config = config
        self.accounts = AccountRepository(db)
        self.tokens = TokenRepository(db)
        self.usage = UsageRepository(db)

    # ── 注册 / 登录 ──────────────────────────────────────────────

    async def register(self, username: str, email: str, password: str) -> dict:
        existing = await self.accounts.find_by_username(username)
        if existing:
            raise DuplicateError("用户名已存在")
        existing = await self.accounts.find_by_email(email)
        if existing:
            raise DuplicateError("邮箱已注册")

        pw_hash = hash_password(password)

        account_id = await self.accounts.create(
            username=username,
            email=email,
            password_hash=pw_hash,
            daily_limit=self._config.default_daily_token_limit,
        )

        return await self._issue_tokens(account_id, username)

    async def login(
        self, username: str, password: str, revoke_others: bool = False
    ) -> dict:
        account = await self.accounts.find_by_username(username)
        if not account:
            raise UnauthorizedError("用户名或密码错误")

        ok, new_hash = verify_password_with_legacy(
            password, account["password_hash"], account.get("password_salt", "")
        )
        if not ok:
            raise UnauthorizedError("用户名或密码错误")

        if new_hash:
            await self.accounts.update_password_hash(account["id"], new_hash)

        if revoke_others:
            await self.tokens.revoke_all_for_account(account["id"])
            await self._db.async_save(
                "DELETE FROM refresh_tokens WHERE account_id = %s", (account["id"],)
            )

        return await self._issue_tokens(account["id"], account["username"])

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

        # 吊销旧 refresh token，签发新的（轮换）
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
        return account

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
        await self.accounts.delete(account_id)

    # ── Token 用量 ─────────────────────────────────────────────

    async def check_quota(self, account_id: int) -> tuple[bool, int, int]:
        return await self.usage.check_limit(account_id)

    async def record_usage(self, account_id: int, tokens: int) -> None:
        if tokens > 0:
            await self.usage.increment_usage(account_id, tokens)

    # ── 内部方法 ──────────────────────────────────────────────────

    async def _issue_tokens(self, account_id: int, username: str) -> dict:
        """签发 access_token + refresh_token，返回完整凭证。"""
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


def _mysql_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
