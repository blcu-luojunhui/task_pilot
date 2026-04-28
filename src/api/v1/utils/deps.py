from __future__ import annotations

from dataclasses import dataclass

from src.core.config import ProjectConfigSettings
from src.infra.database import AsyncMySQLPool
from src.infra.observability import LogService


@dataclass(frozen=True)
class ApiDependencies:
    """API 层依赖容器"""

    mysql: AsyncMySQLPool
    log: LogService
    config: ProjectConfigSettings
