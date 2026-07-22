"""
Yggdrasil 认知架构 —— 数据迁移

DataMigration 负责将现有 Skill、Memory、Knowledge 资产迁移到 tree_node 统一模型。
迁移策略：保留原表数据不变，只向 tree_node 和 node_links 写入新数据。
"""

import json
import logging
from typing import TYPE_CHECKING

from .models import MigrationReport, NodeType, TreeNode
from .store import TreeStore, _DEFAULT_DOMAINS

if TYPE_CHECKING:
    from src.infra.database import AsyncMySQLPool

logger = logging.getLogger("yggdrasil.migration")


class DataMigration:
    """将现有资产迁移到世界树"""

    def __init__(self, store: TreeStore, db: "AsyncMySQLPool"):
        self.store = store
        self.db = db

    async def migrate_all(self) -> MigrationReport:
        """执行全量迁移"""
        report = MigrationReport()

        logger.info("Yggdrasil migration: starting...")

        # 确保骨架存在
        await self.store.ensure_skeleton()

        # 迁移系统技能
        try:
            count = await self._migrate_system_skills()
            report.skills_migrated += count
            logger.info("Yggdrasil migration: %d system_skills migrated", count)
        except Exception as e:
            msg = f"system_skills migration failed: {e}"
            logger.error(msg)
            report.errors.append(msg)

        # 迁移用户技能
        try:
            count = await self._migrate_account_skills()
            report.skills_migrated += count
            logger.info("Yggdrasil migration: %d account_skills migrated", count)
        except Exception as e:
            msg = f"account_skills migration failed: {e}"
            logger.error(msg)
            report.errors.append(msg)

        # 迁移跨 run 记忆
        try:
            count = await self._migrate_agent_memories()
            report.memories_migrated += count
            logger.info("Yggdrasil migration: %d agent_memories migrated", count)
        except Exception as e:
            msg = f"agent_memories migration failed: {e}"
            logger.error(msg)
            report.errors.append(msg)

        # 迁移知识文件
        try:
            count = await self._migrate_knowledge_files()
            report.knowledge_migrated += count
            logger.info("Yggdrasil migration: %d knowledge files migrated", count)
        except Exception as e:
            msg = f"knowledge files migration failed: {e}"
            logger.error(msg)
            report.errors.append(msg)

        logger.info(
            "Yggdrasil migration: complete. %d nodes total, %d errors",
            report.total, len(report.errors),
        )
        return report

    async def rollback(self) -> None:
        """清空 tree_node 和 node_links（保留原表数据不变）"""
        await self.db.async_save("DELETE FROM node_links")
        await self.db.async_save("DELETE FROM tree_node")
        logger.info("Yggdrasil rollback: tree_node and node_links cleared")

    async def _migrate_system_skills(self) -> int:
        """迁移 system_skills 表"""
        try:
            rows = await self.db.async_fetch("SELECT * FROM system_skills")
        except Exception:
            logger.debug("system_skills table may not exist, skipping")
            return 0

        count = 0
        for row in rows:
            category = row.get("category", "general")
            domain = f"/{category}/_skills"
            node_id = f"skill-{row['name']}"

            existing = await self.store.get_node(node_id)
            if existing:
                continue

            node = TreeNode(
                id=node_id,
                parent_id=self._domain_node_id(category, "_skills"),
                domain=domain,
                node_type=NodeType.SKILL,
                title=row["name"],
                content=row.get("content", ""),
                summary=row.get("description", ""),
                metadata={
                    "source_table": "system_skills",
                    "source_id": row["id"],
                    "skill_type": row.get("skill_type", "knowledge"),
                    "scope": row.get("scope", "agent:*"),
                    "tags": [],
                },
            )
            await self.store.create_node(node)
            count += 1

        return count

    async def _migrate_account_skills(self) -> int:
        """迁移 account_skills 表"""
        try:
            rows = await self.db.async_fetch("SELECT * FROM account_skills")
        except Exception:
            logger.debug("account_skills table may not exist, skipping")
            return 0

        count = 0
        for row in rows:
            category = row.get("category", "general")
            domain = f"/{category}/_skills"
            node_id = f"skill-account-{row['account_id']}-{row['name']}"

            existing = await self.store.get_node(node_id)
            if existing:
                continue

            node = TreeNode(
                id=node_id,
                parent_id=self._domain_node_id(category, "_skills"),
                domain=domain,
                node_type=NodeType.SKILL,
                title=row["name"],
                content=row.get("content", ""),
                summary=row.get("description", ""),
                metadata={
                    "source_table": "account_skills",
                    "source_id": row["id"],
                    "account_id": row["account_id"],
                    "scope": row.get("scope", "agent:*"),
                    "tags": [],
                },
            )
            await self.store.create_node(node)
            count += 1

        return count

    async def _migrate_agent_memories(self) -> int:
        """迁移 agent_memory 表"""
        try:
            rows = await self.db.async_fetch("SELECT * FROM agent_memory")
        except Exception:
            logger.debug("agent_memory table may not exist, skipping")
            return 0

        count = 0
        for row in rows:
            scope_key = row.get("scope_key", "general")
            trace_id = row.get("trace_id", "unknown")
            reflection = row.get("reflection", "")

            node_id = f"memory-{trace_id.replace('-', '')[:16]}-{count}"

            existing = await self.store.get_node(node_id)
            if existing:
                node_id = f"memory-{trace_id.replace('-', '')[:16]}-{row['id']}"

            existing = await self.store.get_node(node_id)
            if existing:
                continue

            # 确定 domain：尝试从 scope_key 匹配领域
            domain = self._infer_domain(scope_key, "_memories")

            node = TreeNode(
                id=node_id,
                parent_id=self._domain_node_id_for_domain(domain),
                domain=domain,
                node_type=NodeType.MEMORY,
                title=f"Reflection: {reflection[:80]}",
                content=reflection,
                summary=reflection[:200],
                metadata={
                    "source_table": "agent_memory",
                    "source_id": row["id"],
                    "account_id": row.get("account_id", 0),
                    "scope_key": scope_key,
                    "trace_id": trace_id,
                    "success": bool(row.get("success", 0)),
                },
            )
            await self.store.create_node(node)
            count += 1

        return count

    async def _migrate_knowledge_files(self) -> int:
        """迁移 infra/skill_hub/knowledge/*.md 知识文件"""
        import os
        from pathlib import Path

        knowledge_dir = Path(__file__).parent.parent.parent / "infra" / "skill_hub" / "knowledge"
        if not knowledge_dir.exists():
            logger.debug("Knowledge files directory not found: %s", knowledge_dir)
            return 0

        count = 0
        for md_file in knowledge_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            slug = md_file.stem
            node_id = f"knowledge-{slug}"

            existing = await self.store.get_node(node_id)
            if existing:
                continue

            # 从文件名推断领域
            domain = self._infer_domain_from_filename(slug, "_knowledge")

            # 提取第一行作为标题
            lines = content.strip().split("\n")
            title = lines[0].lstrip("#").strip() if lines else slug

            node = TreeNode(
                id=node_id,
                parent_id=self._domain_node_id_for_domain(domain),
                domain=domain,
                node_type=NodeType.KNOWLEDGE,
                title=title,
                content=content,
                summary=content[:300],
                metadata={
                    "source": "skill_hub",
                    "filename": md_file.name,
                    "tags": [],
                },
            )
            await self.store.create_node(node)
            count += 1

        return count

    # ================================================================
    # 辅助方法
    # ================================================================

    @staticmethod
    def _domain_node_id(category: str, subspace: str) -> str:
        """获取领域子空间节点 ID"""
        return f"domain-{category}-{subspace}"

    @staticmethod
    def _domain_node_id_for_domain(domain: str) -> str:
        """从 domain 路径推断父节点 ID"""
        # domain 格式: /category/_memories/ 或 /category/_skills/
        parts = [p for p in domain.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"domain-{parts[0]}-{parts[1]}"
        elif len(parts) == 1:
            return f"domain-{parts[0]}"
        return "root"

    @staticmethod
    def _infer_domain(scope_key: str, subspace: str) -> str:
        """从 scope_key 推断领域路径"""
        for domain_name in _DEFAULT_DOMAINS:
            if domain_name.lower() in scope_key.lower():
                return f"/{domain_name}/{subspace}/"
        return f"/general/{subspace}/"

    @staticmethod
    def _infer_domain_from_filename(filename: str, subspace: str) -> str:
        """从文件名推断领域路径"""
        for domain_name in _DEFAULT_DOMAINS:
            if domain_name.lower() in filename.lower():
                return f"/{domain_name}/{subspace}/"
        return f"/general/{subspace}/"


__all__ = ["DataMigration"]