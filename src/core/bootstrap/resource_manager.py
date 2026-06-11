import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dependency import ServerContainer

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

        from pathlib import Path

        from src.core.agents.capabilities.skills import get_global_registry
        from src.core.agents.capabilities.skills.loader import SkillLoader

        knowledge_dir = Path(__file__).resolve().parents[2].parent / "skills" / "knowledge"
        if knowledge_dir.exists():
            registry = get_global_registry()
            knowledge_skills = SkillLoader(str(knowledge_dir)).load_all()
            for skill in knowledge_skills:
                registry.register(skill)
            logger.info("Knowledge skills loaded in this worker: %d", len(knowledge_skills))

        logger.info("=== Phase 1: Initializing MySQL pools ===")
        pool = self.container.async_mysql_pool()
        await pool.init_pools()

        logger.info("=== Phase 1.5: Loading system skills from DB ===")
        from src.core.skills.system_repository import SystemSkillRepository
        from src.core.agents.capabilities.skills import get_global_registry
        from src.core.agents.capabilities.skills.model import Skill

        try:
            sys_repo = SystemSkillRepository(pool)
            rows = await sys_repo.list_all()
            registry = get_global_registry()
            for row in rows:
                skill = Skill.knowledge(
                    name=row["name"],
                    description=row["description"],
                    domain=row["category"],
                    scope=row["scope"],
                    content=row.get("content", ""),
                )
                registry.register(skill)
                logger.debug("Loaded system skill from DB: %s", row["name"])
            logger.info("System skills loaded from DB: %d", len(rows))
        except Exception:
            logger.warning("Failed to load system skills from DB (table may not exist yet)", exc_info=True)
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
