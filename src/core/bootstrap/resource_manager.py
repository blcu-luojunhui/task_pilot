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
        logger.info("=== Phase 1: Initializing MySQL pools ===")
        pool = self.container.async_mysql_pool()
        await pool.init_pools()
        logger.info("MySQL pools initialized")

        logger.info("=== Phase 2: Starting log service ===")
        log_service = self.container.log_service()
        await log_service.start()
        logger.info("Log service started")

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
