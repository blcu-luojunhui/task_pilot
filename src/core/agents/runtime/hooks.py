"""
运行时 Hooks - 日志、追踪、回调
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging


@dataclass
class HookContext:
    """Hook 上下文"""

    event_type: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)


class Hook:
    """基础 Hook 接口"""

    async def on_start(self, context: HookContext):
        """开始时触发"""
        pass

    async def on_step(self, context: HookContext):
        """每步触发"""
        pass

    async def on_complete(self, context: HookContext):
        """完成时触发"""
        pass

    async def on_error(self, context: HookContext):
        """错误时触发"""
        pass


class LoggingHook(Hook):
    """日志 Hook"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    async def on_start(self, context: HookContext):
        self.logger.info(f"Agent started: {context.data}")

    async def on_step(self, context: HookContext):
        self.logger.debug(f"Step {context.data.get('step')}: {context.data}")

    async def on_complete(self, context: HookContext):
        self.logger.info(f"Agent completed: {context.data}")

    async def on_error(self, context: HookContext):
        self.logger.error(f"Agent error: {context.data}")


class TracingHook(Hook):
    """追踪 Hook"""

    def __init__(self):
        self.traces: List[HookContext] = []

    async def on_step(self, context: HookContext):
        self.traces.append(context)

    def get_traces(self) -> List[HookContext]:
        return self.traces
