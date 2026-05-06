"""
Fixtures - Mock 工具和环境
"""

from typing import Any, Callable, Dict, Optional
from dataclasses import dataclass


@dataclass
class MockTool:
    """Mock 工具"""
    name: str
    handler: Callable
    return_value: Optional[Any] = None
    side_effect: Optional[Callable] = None

    async def __call__(self, *args, **kwargs):
        if self.side_effect:
            return await self.side_effect(*args, **kwargs)
        return self.return_value


class FixtureManager:
    """
    Fixture 管理器

    用于测试时 mock 工具和环境
    """

    def __init__(self):
        self.mocks: Dict[str, MockTool] = {}
        self.env_vars: Dict[str, str] = {}

    def mock_tool(self, name: str, return_value: Any = None, side_effect: Optional[Callable] = None):
        """Mock 一个工具"""
        mock = MockTool(
            name=name,
            handler=lambda *args, **kwargs: return_value,
            return_value=return_value,
            side_effect=side_effect
        )
        self.mocks[name] = mock
        return mock

    def set_env(self, key: str, value: str):
        """设置环境变量"""
        self.env_vars[key] = value

    def get_mock(self, name: str) -> Optional[MockTool]:
        """获取 mock 工具"""
        return self.mocks.get(name)

    def clear(self):
        """清空所有 fixtures"""
        self.mocks.clear()
        self.env_vars.clear()
