"""
协议定义 - Skills 系统的核心接口

定义可扩展的协议，支持自定义实现
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .model import Skill


@runtime_checkable
class DependencyResolver(Protocol):
    """依赖解析器协议"""

    def resolve(self, dep_name: str) -> Any:
        """
        解析依赖名称为具体对象

        Args:
            dep_name: 依赖名称（如 "db", "http", "log"）

        Returns:
            依赖对象实例
        """
        ...


@runtime_checkable
class ToolSpecAdapter(Protocol):
    """工具描述适配器协议"""

    def to_spec(self, skill: Skill) -> Dict[str, Any]:
        """
        将 Skill 转换为特定格式的工具描述

        Args:
            skill: Skill 对象

        Returns:
            工具描述字典
        """
        ...


@runtime_checkable
class MarkdownParser(Protocol):
    """Markdown 解析器协议"""

    def can_parse(self, content: str) -> bool:
        """
        判断是否能解析该内容

        Args:
            content: Markdown 内容

        Returns:
            是否支持解析
        """
        ...

    def parse(self, content: str, filename: str) -> Optional[Skill]:
        """
        解析 Markdown 内容为 Skill

        Args:
            content: Markdown 内容
            filename: 文件名（不含扩展名）

        Returns:
            Skill 对象，解析失败返回 None
        """
        ...


__all__ = ["DependencyResolver", "ToolSpecAdapter", "MarkdownParser"]
