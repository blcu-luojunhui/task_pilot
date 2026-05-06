from __future__ import annotations

from dataclasses import dataclass

from src.core.config import ProjectConfigSettings
from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService, AlertService
from src.infra.streaming import TraceEventBus
from src.jobs.task_lifecycle import TaskLifecycleManager


@dataclass(frozen=True)
class ApiDependencies:
    """API 层依赖容器"""

    mysql: AsyncMySQLPool
    log: LogService
    config: ProjectConfigSettings
    alert: AlertService
    lifecycle: TaskLifecycleManager
    events: TraceEventBus

    # 向后兼容别名
    @property
    def db(self) -> AsyncMySQLPool:
        return self.mysql
