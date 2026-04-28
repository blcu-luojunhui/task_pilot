import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.dependency import ServerContainer

logger = logging.getLogger(__name__)


class AppContext:
    def __init__(self, container: "ServerContainer"):
        self.container = container

    async def start_up(self):
        logger.info("Initializing mysql pools")
        pool = self.container.async_mysql_pool()
        await pool.init_pools()
        logger.info("MySQL pools initialized")

        logger.info("Starting log service")
        log_service = self.container.log_service()
        await log_service.start()
        logger.info("Log service started")

    async def shutdown(self):
        logger.info("Closing database pools")
        pool = self.container.async_mysql_pool()
        await pool.close_pools()
        logger.info("Application resources released")


__all__ = ["AppContext"]
