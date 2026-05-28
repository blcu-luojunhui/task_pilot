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
            "SELECT id, username, email, password_hash, password_salt, "
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
