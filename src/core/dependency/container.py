from dependency_injector import containers, providers

from src.core.config import GlobalConfigSettings
from src.core.database import DatabaseManager
from src.core.observability import LogService


class ServerContainer(containers.DeclarativeContainer):
    config = providers.Singleton(GlobalConfigSettings)

    log_service = providers.Singleton(LogService, log_config=config.provided.log)

    mysql_manager = providers.Singleton(
        DatabaseManager, config=config, log_service=log_service
    )


__all__ = ["ServerContainer"]
