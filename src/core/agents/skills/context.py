"""
Skill 执行上下文

按需注入 Skill 声明的依赖
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from .types import DependencyResolver

if TYPE_CHECKING:
    from src.core.dependency import ServerContainer
    from src.infra.database import AsyncMySQLPool
    from src.infra.observability import LogService
    from src.infra.shared import AsyncHttpClient
    from src.core.config import ProjectConfigSettings


class ContainerResolver:
    """基于 ServerContainer 的依赖解析器"""

    def __init__(self, container: "ServerContainer"):
        self.container = container
        self._cache: Dict[str, Any] = {}

    def resolve(self, dep_name: str) -> Any:
        """解析依赖"""
        # 使用缓存避免重复创建
        if dep_name in self._cache:
            return self._cache[dep_name]

        if dep_name == "db":
            obj = self.container.async_mysql_pool()
        elif dep_name == "http":
            # AsyncHttpClient 需要手动实例化
            from src.infra.shared import AsyncHttpClient
            obj = AsyncHttpClient()
        elif dep_name == "log":
            obj = self.container.log_service()
        elif dep_name == "config":
            obj = self.container.config()
        else:
            raise ValueError(f"Unknown dependency: {dep_name}")

        self._cache[dep_name] = obj
        return obj


@dataclass
class SkillContext:
    """Skill 执行上下文"""

    _resolver: DependencyResolver
    _cache: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __getattr__(self, name: str) -> Any:
        """动态解析依赖"""
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        if name not in self._cache:
            self._cache[name] = self._resolver.resolve(name)

        return self._cache[name]

    @classmethod
    def build(cls, skill: Any, container: "ServerContainer") -> "SkillContext":
        """
        根据 Skill 声明的 dependencies 构建最小上下文

        Args:
            skill: Skill 对象（需要有 dependencies 属性）
            container: ServerContainer 实例

        Returns:
            SkillContext 实例
        """
        resolver = ContainerResolver(container)

        # 预加载 Skill 声明的依赖
        ctx = cls(_resolver=resolver)
        for dep in skill.dependencies:
            _ = getattr(ctx, dep)  # 触发解析并缓存

        return ctx

    @classmethod
    def from_resolver(cls, resolver: DependencyResolver) -> "SkillContext":
        """从自定义 Resolver 创建上下文"""
        return cls(_resolver=resolver)


__all__ = ["SkillContext", "ContainerResolver"]
