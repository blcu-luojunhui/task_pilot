from __future__ import annotations

from dataclasses import dataclass

from src.core.config import GlobalConfigSettings
from src.core.database import DatabaseManager
from src.core.observability import LogService


@dataclass(frozen=True)
class ApiDependencies:
    """API 层依赖容器"""

    db: DatabaseManager
    log: LogService
    config: GlobalConfigSettings
