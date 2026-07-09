from __future__ import annotations

from datetime import date
from typing import Optional

from src.infra.database import AsyncMySQLPool


class AccountRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def create(
        self, username: str, email: str, password_hash: str, daily_limit: int
    ) -> int:
        sql = (
            "INSERT INTO accounts (username, email, password_hash, daily_token_limit) "
            "VALUES (%s, %s, %s, %s)"
        )
        return await self._db.async_save(
            sql, (username, email, password_hash, daily_limit),
            return_lastrowid=True,
        )

    async def find_by_id(self, account_id: int) -> Optional[dict]:
        return await self._db.async_fetch_one(
            "SELECT id, username, email, role, avatar_url, agent_avatar_url, "
            "password_hash, password_salt, "
            "daily_token_limit, created_at, updated_at "
            "FROM accounts WHERE id = %s",
            params=(account_id,),
        )

    async def find_by_username(self, username: str) -> Optional[dict]:
        return await self._db.async_fetch_one(
            "SELECT * FROM accounts WHERE username = %s", params=(username,)
        )

    async def find_by_email(self, email: str) -> Optional[dict]:
        return await self._db.async_fetch_one(
            "SELECT * FROM accounts WHERE email = %s", params=(email,)
        )

    async def update_password_hash(self, account_id: int, new_hash: str) -> None:
        await self._db.async_save(
            "UPDATE accounts SET password_hash = %s, password_salt = '' WHERE id = %s",
            (new_hash, account_id),
        )

    async def update_email(self, account_id: int, email: str) -> None:
        await self._db.async_save(
            "UPDATE accounts SET email = %s WHERE id = %s",
            (email, account_id),
        )

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        total_row = await self._db.async_fetch_one(
            "SELECT COUNT(*) AS c FROM accounts"
        )
        total = total_row["c"] if total_row else 0
        rows = await self._db.async_fetch(
            "SELECT id, username, email, role, daily_token_limit, created_at, updated_at "
            "FROM accounts ORDER BY id ASC LIMIT %s OFFSET %s",
            params=(page_size, (page - 1) * page_size),
        )
        return rows, total

    async def update_role(self, account_id: int, role: str) -> bool:
        affected = await self._db.async_save(
            "UPDATE accounts SET role = %s WHERE id = %s", (role, account_id)
        )
        return affected > 0

    async def update_daily_limit(self, account_id: int, limit: int) -> bool:
        affected = await self._db.async_save(
            "UPDATE accounts SET daily_token_limit = %s WHERE id = %s",
            (limit, account_id),
        )
        return affected > 0

    async def update_avatar_url(
        self, account_id: int, role: str, version_key: str | None
    ) -> bool:
        column = "avatar_url" if role == "user" else "agent_avatar_url"
        affected = await self._db.async_save(
            f"UPDATE accounts SET {column} = %s WHERE id = %s",
            (version_key, account_id),
        )
        return affected > 0

    async def delete(self, account_id: int) -> None:
        await self._db.async_save(
            "DELETE FROM account_daily_usage WHERE account_id = %s", (account_id,)
        )
        await self._db.async_save(
            "DELETE FROM refresh_tokens WHERE account_id = %s", (account_id,)
        )
        await self._db.async_save(
            "DELETE FROM access_tokens WHERE account_id = %s", (account_id,)
        )
        await self._db.async_save(
            "DELETE FROM accounts WHERE id = %s", (account_id,)
        )


class TokenRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def create(
        self,
        account_id: int,
        token_hash: str,
        token_prefix: str,
        name: Optional[str],
        expires_at: Optional[str],
    ) -> int:
        sql = (
            "INSERT INTO access_tokens (account_id, token_hash, token_prefix, name, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        return await self._db.async_save(
            sql, (account_id, token_hash, token_prefix, name, expires_at),
            return_lastrowid=True,
        )

    async def find_by_hash(self, token_hash: str) -> Optional[dict]:
        return await self._db.async_fetch_one(
            "SELECT t.id, t.account_id, t.token_hash, t.token_prefix, t.name, "
            "t.expires_at, t.created_at, "
            "a.username, a.daily_token_limit "
            "FROM access_tokens t "
            "JOIN accounts a ON a.id = t.account_id "
            "WHERE t.token_hash = %s",
            params=(token_hash,),
        )

    async def update_last_used(self, token_id: int) -> None:
        await self._db.async_save(
            "UPDATE access_tokens SET last_used_at = NOW() WHERE id = %s", (token_id,)
        )

    async def list_by_account(self, account_id: int) -> list[dict]:
        return await self._db.async_fetch(
            "SELECT id, token_prefix, name, last_used_at, expires_at, created_at "
            "FROM access_tokens WHERE account_id = %s ORDER BY created_at DESC",
            params=(account_id,),
        )

    async def delete(self, token_id: int, account_id: int) -> bool:
        affected = await self._db.async_save(
            "DELETE FROM access_tokens WHERE id = %s AND account_id = %s",
            (token_id, account_id),
        )
        return affected > 0

    async def revoke_all_for_account(self, account_id: int) -> int:
        return await self._db.async_save(
            "DELETE FROM access_tokens WHERE account_id = %s", (account_id,)
        )


class UsageRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def get_today_usage(self, account_id: int) -> dict:
        today = date.today().isoformat()
        row = await self._db.async_fetch_one(
            "SELECT tokens_used FROM account_daily_usage WHERE account_id = %s AND usage_date = %s",
            params=(account_id, today),
        )
        return {"tokens_used": row["tokens_used"] if row else 0}

    async def check_limit(self, account_id: int) -> tuple[bool, int, int]:
        account = await self._db.async_fetch_one(
            "SELECT daily_token_limit FROM accounts WHERE id = %s", params=(account_id,)
        )
        if not account:
            return False, 0, 0

        limit = account["daily_token_limit"]
        usage = await self.get_today_usage(account_id)
        used = usage["tokens_used"]
        return used < limit, used, limit

    async def increment_usage(self, account_id: int, tokens: int) -> None:
        today = date.today().isoformat()
        await self._db.async_save(
            "INSERT INTO account_daily_usage (account_id, usage_date, tokens_used) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE tokens_used = tokens_used + %s",
            (account_id, today, tokens, tokens),
        )


class InviteCodeRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def create_batch(self, created_by: int, codes: list[str]) -> list[str]:
        """批量插入邀请码，返回 codes 列表。"""
        for code in codes:
            await self._db.async_save(
                "INSERT INTO invite_codes (code, created_by) VALUES (%s, %s)",
                (code, created_by),
            )
        return codes

    async def find_by_code(self, code: str) -> Optional[dict]:
        return await self._db.async_fetch_one(
            "SELECT id, code, created_by, used_by, status, created_at, used_at "
            "FROM invite_codes WHERE code = %s",
            params=(code,),
        )

    async def reserve(self, code: str) -> bool:
        """原子预占邀请码（used_by=0 占位），防止并发重复使用。"""
        affected = await self._db.async_save(
            "UPDATE invite_codes SET status = 1, used_by = 0, used_at = NOW() "
            "WHERE code = %s AND status = 0",
            (code,),
        )
        return affected > 0

    async def assign(self, code: str, account_id: int) -> None:
        """将预占的邀请码绑定到真实账户。"""
        await self._db.async_save(
            "UPDATE invite_codes SET used_by = %s WHERE code = %s",
            (account_id, code),
        )

    async def release(self, code: str) -> None:
        """释放预占的邀请码（注册失败回滚）。"""
        await self._db.async_save(
            "UPDATE invite_codes SET status = 0, used_by = NULL, used_at = NULL WHERE code = %s",
            (code,),
        )

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        total_row = await self._db.async_fetch_one(
            "SELECT COUNT(*) AS c FROM invite_codes"
        )
        total = total_row["c"] if total_row else 0
        rows = await self._db.async_fetch(
            "SELECT ic.id, ic.code, ic.created_by, ic.used_by, ic.status, "
            "ic.created_at, ic.used_at, a.username AS created_by_name "
            "FROM invite_codes ic "
            "LEFT JOIN accounts a ON a.id = ic.created_by "
            "ORDER BY ic.id DESC LIMIT %s OFFSET %s",
            params=(page_size, (page - 1) * page_size),
        )
        return rows, total


class LoginFailureRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def record_failure(self, account_id: int, ip: str) -> None:
        await self._db.async_save(
            "INSERT INTO account_login_failures (account_id, ip_address, fail_count, first_fail_at, last_fail_at) "
            "VALUES (%s, %s, 1, NOW(), NOW()) "
            "ON DUPLICATE KEY UPDATE fail_count = fail_count + 1, ip_address = %s, last_fail_at = NOW()",
            (account_id, ip, ip),
        )

    async def lock_account(self, account_id: int, lock_minutes: int) -> None:
        await self._db.async_save(
            "UPDATE account_login_failures SET locked_until = DATE_ADD(NOW(), INTERVAL %s MINUTE) "
            "WHERE account_id = %s",
            (lock_minutes, account_id),
        )

    async def check_locked(self, account_id: int) -> tuple[bool, int]:
        """返回 (is_locked, remaining_seconds)。"""
        row = await self._db.async_fetch_one(
            "SELECT fail_count, locked_until, "
            "TIMESTAMPDIFF(SECOND, NOW(), locked_until) AS remaining_sec "
            "FROM account_login_failures WHERE account_id = %s",
            params=(account_id,),
        )
        if not row or not row["locked_until"]:
            return False, 0
        remaining = row["remaining_sec"] or 0
        if remaining > 0:
            return True, remaining
        return False, 0

    async def reset_failures(self, account_id: int) -> None:
        await self._db.async_save(
            "DELETE FROM account_login_failures WHERE account_id = %s",
            (account_id,),
        )
