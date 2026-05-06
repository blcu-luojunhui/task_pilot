from dependency_injector import containers, providers

from src.core.config import ProjectConfigSettings

from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService, AlertService
from src.infra.shared import AsyncHttpClient
from src.infra.streaming import TraceEventBus
from src.jobs.task_lifecycle import TaskLifecycleManager


class ServerContainer(containers.DeclarativeContainer):
    config = providers.Singleton(ProjectConfigSettings)

    log_service = providers.Singleton(LogService, log_config=config.provided.log)

    async_mysql_pool = providers.Singleton(
        AsyncMySQLPool, config=config.provided.task_pilot_mysql, log_service=log_service
    )

    alert_service = providers.Singleton(
        AlertService,
        alert_backend=None,
        max_queue_size=config.provided.alert.queue_size,
    )

    http_client = providers.Singleton(
        AsyncHttpClient,
        timeout=10,
        max_connections=100,
    )

    task_lifecycle_manager = providers.Singleton(
        TaskLifecycleManager,
        db_client=async_mysql_pool,
        poll_interval=5.0,
        force_kill_timeout=10.0,
        task_table=config.provided.task_table,
    )

    trace_event_bus = providers.Singleton(TraceEventBus)


__all__ = ["ServerContainer"]
