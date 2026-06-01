from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.skills.markdown import extract_personal_fields
from src.infra.database import AsyncMySQLPool


class PersonalSkillRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def list_by_account(self, account_id: int) -> List[Dict[str, Any]]:
        rows = await self._db.async_fetch(
            "SELECT id, account_id, name, category, description, scope, content, "
            "created_at, updated_at "
            "FROM account_skills WHERE account_id = %s ORDER BY category, name",
            params=(account_id,),
        )
        return rows

    async def get_by_id(self, account_id: int, skill_id: int) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            "SELECT id, account_id, name, category, description, scope, content, "
            "created_at, updated_at "
            "FROM account_skills WHERE id = %s AND account_id = %s",
            params=(skill_id, account_id),
        )

    async def create(
        self,
        account_id: int,
        *,
        name: str,
        category: str,
        description: str,
        scope: str,
        content: str,
    ) -> int:
        return await self._db.async_save(
            "INSERT INTO account_skills "
            "(account_id, name, category, description, scope, content) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (account_id, name, category, description, scope, content),
            return_lastrowid=True,
        )

    async def update(
        self,
        account_id: int,
        skill_id: int,
        *,
        name: str,
        category: str,
        description: str,
        scope: str,
        content: str,
    ) -> bool:
        affected = await self._db.async_save(
            "UPDATE account_skills SET name = %s, category = %s, description = %s, "
            "scope = %s, content = %s "
            "WHERE id = %s AND account_id = %s",
            (name, category, description, scope, content, skill_id, account_id),
        )
        return affected > 0

    async def delete(self, account_id: int, skill_id: int) -> bool:
        affected = await self._db.async_save(
            "DELETE FROM account_skills WHERE id = %s AND account_id = %s",
            (skill_id, account_id),
        )
        return affected > 0

    async def upsert_from_markdown(self, account_id: int, content: str) -> Dict[str, Any]:
        fields = extract_personal_fields(content)
        name = fields["name"]
        category = fields["category"]
        description = fields["description"]
        scope = fields["scope"]

        existing = await self._db.async_fetch_one(
            "SELECT id FROM account_skills WHERE account_id = %s AND name = %s",
            params=(account_id, name),
        )
        if existing:
            await self.update(
                account_id,
                int(existing["id"]),
                name=name,
                category=category,
                description=description,
                scope=scope,
                content=content,
            )
            row = await self.get_by_id(account_id, int(existing["id"]))
        else:
            skill_id = await self.create(
                account_id,
                name=name,
                category=category,
                description=description,
                scope=scope,
                content=content,
            )
            row = await self.get_by_id(account_id, skill_id)

        if not row:
            raise RuntimeError("Failed to persist personal skill")
        return row


__all__ = ["PersonalSkillRepository"]
