from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.infra.database import AsyncMySQLPool


class SystemSkillRepository:
    def __init__(self, db: AsyncMySQLPool):
        self._db = db

    async def list_all(self) -> List[Dict[str, Any]]:
        return await self._db.async_fetch(
            "SELECT id, name, category, description, scope, content, skill_type, "
            "created_at, updated_at "
            "FROM system_skills ORDER BY category, name"
        )

    async def get_by_id(self, skill_id: int) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            "SELECT id, name, category, description, scope, content, skill_type, "
            "created_at, updated_at "
            "FROM system_skills WHERE id = %s",
            params=(skill_id,),
        )

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            "SELECT id, name, category, description, scope, content, skill_type, "
            "created_at, updated_at "
            "FROM system_skills WHERE name = %s",
            params=(name,),
        )

    async def create(
        self,
        *,
        name: str,
        category: str,
        description: str,
        scope: str,
        content: str,
        skill_type: str = "knowledge",
    ) -> int:
        return await self._db.async_save(
            "INSERT INTO system_skills (name, category, description, scope, content, skill_type) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (name, category, description, scope, content, skill_type),
            return_lastrowid=True,
        )

    async def update(
        self,
        skill_id: int,
        *,
        name: str,
        category: str,
        description: str,
        scope: str,
        content: str,
    ) -> bool:
        affected = await self._db.async_save(
            "UPDATE system_skills SET name = %s, category = %s, description = %s, "
            "scope = %s, content = %s WHERE id = %s",
            (name, category, description, scope, content, skill_id),
        )
        return affected > 0

    async def delete(self, skill_id: int) -> bool:
        affected = await self._db.async_save(
            "DELETE FROM system_skills WHERE id = %s", (skill_id,)
        )
        return affected > 0


__all__ = ["SystemSkillRepository"]
