"""
Skill 注册表

统一管理可执行技能和知识型技能，支持标签过滤和命名空间
"""

import logging
from typing import Callable, Dict, List, Optional, Any

from .model import Skill, SkillType
from .loader import SkillLoader
from .serializer import ToolSpecSerializer, OpenAIAdapter
from .types import ToolSpecAdapter

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册表"""

    def __init__(self, namespace: str = "default", adapter: Optional[ToolSpecAdapter] = None):
        self.namespace = namespace
        self._skills: Dict[str, Skill] = {}
        self._serializer = ToolSpecSerializer(adapter or OpenAIAdapter())

    def register(self, skill: Skill) -> None:
        """注册技能"""
        if skill.name in self._skills:
            logger.warning(f"Skill '{skill.name}' already registered, overwriting")
        self._skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name} ({skill.skill_type.value})")

    def unregister(self, name: str) -> bool:
        """注销技能"""
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        """按名称查找技能"""
        return self._skills.get(name)

    def filter(self, predicate: Callable[[Skill], bool]) -> List[Skill]:
        """自定义过滤"""
        return [s for s in self._skills.values() if predicate(s)]

    def list_executable(self) -> List[Skill]:
        """列出所有可执行技能"""
        return self.filter(lambda s: s.is_executable)

    def list_knowledge(self, domain: Optional[str] = None) -> List[Skill]:
        """列出知识型技能"""
        skills = self.filter(lambda s: s.is_knowledge)
        if domain:
            skills = [s for s in skills if s.domain == domain]
        return skills

    def list_by_tags(self, tags: List[str]) -> List[Skill]:
        """按标签过滤"""
        tag_set = set(tags)
        return self.filter(lambda s: bool(tag_set & set(s.tags)))

    def to_tool_specs(self) -> List[Dict[str, Any]]:
        """生成所有可执行技能的工具描述（结构化）"""
        return self._serializer.serialize_many(self.list_executable())

    def to_tools_prompt(self) -> str:
        """生成所有可执行技能的工具描述（文本）"""
        return self._serializer.to_prompt(self.list_executable())

    def to_knowledge_prompt(self, domain: Optional[str] = None) -> str:
        """生成知识型技能的 prompt 文本"""
        knowledge_skills = self.list_knowledge(domain=domain)
        if not knowledge_skills:
            return ""

        lines = []
        for skill in knowledge_skills:
            lines.append(skill.to_prompt_text())
            lines.append("")
        return "\n".join(lines)

    def load_from_directory(self, path: str) -> int:
        """从目录批量加载 Markdown 知识技能"""
        loader = SkillLoader(path)
        skills = loader.load_all()
        for skill in skills:
            self.register(skill)
        return len(skills)

    @property
    def size(self) -> int:
        return len(self._skills)


# 全局注册表
_global_registry = SkillRegistry()


def skill(
    name: str,
    description: str,
    dependencies: Optional[List[str]] = None,
    parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    scope: str = "agent:*",
    domain: str = "general",
    tags: Optional[List[str]] = None,
):
    """
    装饰器：注册可执行技能

    Example:
        @skill(
            name="query_articles",
            description="查询文章列表",
            dependencies=["db"],
            parameters={
                "date": {"type": "string", "description": "日期"},
                "limit": {"type": "integer", "description": "数量", "default": 10},
            },
        )
        async def query_articles(ctx, date: str, limit: int = 10):
            return await ctx.db.async_fetch(...)
    """

    def decorator(func: Callable):
        skill_obj = Skill.executable(
            name=name,
            description=description,
            handler=func,
            parameters=parameters or {},
            dependencies=dependencies or [],
            scope=scope,
            domain=domain,
            tags=tags or [],
        )
        _global_registry.register(skill_obj)
        return func

    return decorator


def get_global_registry() -> SkillRegistry:
    """获取全局技能注册表"""
    return _global_registry


__all__ = ["SkillRegistry", "skill", "get_global_registry"]
