from dependency_injector import containers, providers

from src.core.config import ProjectConfigSettings
from src.core.chat.service import ChatService
from src.core.auth import AuthService

from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService, AlertService
from src.infra.shared import AsyncHttpClient
from src.infra.streaming import TraceEventBus, EventPersister
from src.jobs.task_lifecycle import TaskLifecycleManager
from src.core.yggdrasil import TreeStore, EmbeddingService, TreeRetriever, ContextAssembler


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

    event_persister = providers.Singleton(
        EventPersister,
        mysql_pool=async_mysql_pool,
    )

    trace_event_bus = providers.Singleton(
        TraceEventBus,
        persister=event_persister,
    )

    chat_service = providers.Singleton(
        ChatService,
        db=async_mysql_pool,
        log=log_service,
        config=config,
        event_bus=trace_event_bus,
    )

    auth_service = providers.Singleton(
        AuthService,
        db=async_mysql_pool,
        config=config.provided.auth,
    )

    # ============ Yggdrasil 认知架构 ============
    yggdrasil_config = providers.Singleton(lambda: config().yggdrasil)

    yggdrasil_store = providers.Singleton(
        TreeStore,
        db=async_mysql_pool,
        config=yggdrasil_config,
    )

    yggdrasil_embedding = providers.Singleton(
        EmbeddingService,
        config=yggdrasil_config,
        llm_provider=None,  # 使用 mock embedding，后续可注入 LLM provider
    )

    yggdrasil_retriever = providers.Singleton(
        TreeRetriever,
        store=yggdrasil_store,
        embedding=yggdrasil_embedding,
        config=yggdrasil_config,
    )

    yggdrasil_assembler = providers.Singleton(ContextAssembler)


__all__ = ["ServerContainer"]
