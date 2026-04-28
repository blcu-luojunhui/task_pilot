from dependency_injector import containers, providers

from src.core.config import ProjectConfigSettings

from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService


class ServerContainer(containers.DeclarativeContainer):
    config = providers.Singleton(ProjectConfigSettings)

    log_service = providers.Singleton(LogService, log_config=config.provided.log)

    async_mysql_pool = providers.Singleton(
        AsyncMySQLPool, config=config.provided.task_pilot_mysql, log_service=log_service
    )


__all__ = ["ServerContainer"]
