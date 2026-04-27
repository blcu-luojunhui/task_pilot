from __future__ import annotations

from quart import Blueprint

from src.api.v1.utils import ApiDependencies
from src.api.v1.endpoints import create_health_bp, create_tasks_bp
from src.core.config import GlobalConfigSettings
from src.core.database import DatabaseManager
from src.core.observability import LogService


def register_v1_blueprints(deps: ApiDependencies) -> Blueprint:
    api = Blueprint("api", __name__, url_prefix="/api")

    api.register_blueprint(create_health_bp())
    api.register_blueprint(create_tasks_bp(deps))

    return api


def server_routes(
    pools: DatabaseManager, log_service: LogService, config: GlobalConfigSettings
) -> Blueprint:
    deps = ApiDependencies(db=pools, log=log_service, config=config)
    return register_v1_blueprints(deps)
