import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dependency import ServerContainer

from src.core.yggdrasil.store import _DEFAULT_DOMAINS

logger = logging.getLogger(__name__)


class AppContext:
    """
    应用上下文管理器

    统一管理所有资源的启动和关闭生命周期
    """

    def __init__(self, container: "ServerContainer"):
        self.container = container

    async def start_up(self):
        """启动所有资源"""
        logger.info("=== Phase 0: Loading agentic tools into global registry ===")
        from src.core.agents.capabilities.tools.loader import load_agentic_tools

        loaded = load_agentic_tools(["database", "http", "task", "utils", "chat_ops"])
        logger.info("Agentic tools loaded in this worker: %s", ", ".join(loaded))

        logger.info("=== Phase 1: Initializing MySQL pools ===")
        pool = self.container.async_mysql_pool()
        await pool.init_pools()

        logger.info("=== Phase 1.5: Loading skills from skill_registry ===")
        from src.core.skill_store import SkillStoreRepository
        from src.core.agents.capabilities.skills import get_global_registry

        try:
            store_repo = SkillStoreRepository(pool)
            rows = await store_repo.load_all_for_agent()
            registry = get_global_registry()
            loaded = registry.load_from_db_rows(rows)
            logger.info("Skills loaded from skill_registry: %d", loaded)
        except Exception:
            logger.warning("Failed to load skills from skill_registry (table may not exist yet)", exc_info=True)

        logger.info("=== Phase 1.6: Loading system_skills from DB (legacy) ===")
        from src.core.skills.system_repository import SystemSkillRepository
        from src.core.agents.capabilities.skills.model import Skill

        try:
            sys_repo = SystemSkillRepository(pool)
            sys_rows = await sys_repo.list_all()
            registry = get_global_registry()
            for row in sys_rows:
                skill = Skill.knowledge(
                    name=row["name"],
                    description=row["description"],
                    domain=row["category"],
                    scope=row["scope"],
                    content=row.get("content", ""),
                )
                registry.register(skill)
                logger.debug("Loaded system skill from DB: %s", row["name"])
            logger.info("System skills loaded from DB: %d", len(sys_rows))
        except Exception:
            logger.warning("Failed to load system_skills from DB (table may not exist yet)", exc_info=True)
        logger.info("MySQL pools initialized")

        logger.info("=== Phase 2: Starting log service ===")
        log_service = self.container.log_service()
        await log_service.start()
        logger.info("Log service started")

        logger.info("=== Phase 2.5: Starting event persister ===")
        persister = self.container.event_persister()
        await persister.start()
        logger.info("Event persister started")

        logger.info("=== Phase 3: Starting alert service ===")
        alert_service = self.container.alert_service()
        await alert_service.start()
        logger.info("Alert service started")

        logger.info("=== Phase 4: Starting task lifecycle manager ===")
        lifecycle = self.container.task_lifecycle_manager()
        await lifecycle.start_polling()
        logger.info("Task lifecycle manager started")

        logger.info("=== Phase 5: Starting shared HTTP client ===")
        http_client = self.container.http_client()
        await http_client.start()
        logger.info("Shared HTTP client started")

        logger.info("=== Phase 6: Initializing Yggdrasil world tree ===")
        try:
            yggdrasil_config = self.container.yggdrasil_config()
            if yggdrasil_config.enabled:
                yggdrasil_store = self.container.yggdrasil_store()
                await yggdrasil_store.ensure_skeleton()

                # 检查是否需要迁移
                node_count = await yggdrasil_store.count_nodes()
                if node_count <= len(_DEFAULT_DOMAINS) * 3 + 1:  # 只有骨架节点
                    from src.core.yggdrasil.migration import DataMigration
                    migration = DataMigration(
                        store=yggdrasil_store,
                        db=self.container.async_mysql_pool(),
                    )
                    report = await migration.migrate_all()
                    logger.info(
                        "Yggdrasil migration: %d skills, %d knowledge, %d memories (%d errors)",
                        report.skills_migrated, report.knowledge_migrated,
                        report.memories_migrated, len(report.errors),
                    )

                # 初始化 ChromaDB 索引
                yggdrasil_embedding = self.container.yggdrasil_embedding()
                await yggdrasil_embedding.initialize()
                logger.info("Yggdrasil: ChromaDB initialized")
            else:
                logger.info("Yggdrasil: disabled, skipping initialization")
        except Exception:
            logger.warning("Yggdrasil initialization failed, continuing without it", exc_info=True)

        logger.info("=== Application startup complete ===")

    async def shutdown(self):
        """关闭所有资源（优雅关闭）"""
        logger.info("=== Phase 1: Stopping task lifecycle manager ===")
        lifecycle = self.container.task_lifecycle_manager()
        await lifecycle.shutdown(timeout=30.0)
        logger.info("All tasks cancelled/completed")

        logger.info("=== Phase 2: Stopping alert service ===")
        alert_service = self.container.alert_service()
        await alert_service.stop(drain_timeout=5.0)
        logger.info("Alert service stopped")

        logger.info("=== Phase 3: Stopping log service ===")
        log_service = self.container.log_service()
        await log_service.stop(drain_timeout=10.0)
        logger.info("Log service stopped")

        logger.info("=== Phase 3.5: Stopping event persister ===")
        persister = self.container.event_persister()
        await persister.stop(grace_seconds=5.0)
        logger.info("Event persister stopped")

        logger.info("=== Phase 4: Closing database pools ===")
        pool = self.container.async_mysql_pool()
        await pool.close_pools()
        logger.info("Database pools closed")

        logger.info("=== Phase 5: Closing shared HTTP client ===")
        http_client = self.container.http_client()
        await http_client.close()
        logger.info("Shared HTTP client closed")

        logger.info("=== Application shutdown complete ===")


__all__ = ["AppContext"]
