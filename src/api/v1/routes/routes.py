from __future__ import annotations

from quart import Blueprint

from src.api.v1.utils import ApiDependencies
from src.api.v1.endpoints import create_health_bp, create_tasks_bp, create_metrics_bp
from src.core.config import ProjectConfigSettings
from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService, AlertService
from src.infra.streaming import TraceEventBus
from src.jobs.task_lifecycle import TaskLifecycleManager


def register_v1_blueprints(deps: ApiDependencies) -> Blueprint:
    api = Blueprint("api", __name__, url_prefix="/api")

    api.register_blueprint(create_health_bp(deps))
    api.register_blueprint(create_tasks_bp(deps))
    api.register_blueprint(create_metrics_bp(deps))

    return api


def server_routes(
    pools: AsyncMySQLPool,
    log_service: LogService,
    config: ProjectConfigSettings,
    alert_service: AlertService,
    lifecycle: TaskLifecycleManager,
    events: TraceEventBus,
) -> Blueprint:
    deps = ApiDependencies(
        mysql=pools,
        log=log_service,
        config=config,
        alert=alert_service,
        lifecycle=lifecycle,
        events=events,
    )
    return register_v1_blueprints(deps)
