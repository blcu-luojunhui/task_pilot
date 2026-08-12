"""
Capabilities Layer - 能力层

提供 Agent 的核心能力：
- skill_hub: 技能系统
- tools: 工具集合
- llm: LLM 集成
"""

from .skills import (
    Skill,
    SkillType,
    RiskLevel,
    SkillContext,
    ContainerResolver,
    MappingResolver,
    SkillExecutor,
    SkillExecutionError,
    execute_skill,
    SkillRegistry,
    skill,
    get_global_registry,
    FrontmatterParser,
    InlineMetadataParser,
    OpenAIAdapter,
    ClaudeAdapter,
    ToolSpecSerializer,
    ParameterValidator,
    SkillValidationError,
    PermissionGuard,
    ToolPolicy,
    ToolPolicyError,
    ToolOutput,
    DependencyResolver,
    ToolSpecAdapter,
    MarkdownParser,
)
from .tools import (
    TOOL_AREAS,
    DEFAULT_TOOL_AREAS,
    load_agentic_tools,
)


_LEGACY_LLM_EXPORTS = {"DeepSeekPlanner", "DeepSeekSettings", "load_dotenv"}


def __getattr__(name: str):
    if name not in _LEGACY_LLM_EXPORTS:
        raise AttributeError(name)
    from . import llm

    return getattr(llm, name)

__all__ = [
    # Skills
    "Skill",
    "SkillType",
    "RiskLevel",
    "SkillContext",
    "ContainerResolver",
    "MappingResolver",
    "SkillExecutor",
    "SkillExecutionError",
    "execute_skill",
    "SkillRegistry",
    "skill",
    "get_global_registry",
    "FrontmatterParser",
    "InlineMetadataParser",
    "OpenAIAdapter",
    "ClaudeAdapter",
    "ToolSpecSerializer",
    "ParameterValidator",
    "SkillValidationError",
    "PermissionGuard",
    "ToolPolicy",
    "ToolPolicyError",
    "ToolOutput",
    "DependencyResolver",
    "ToolSpecAdapter",
    "MarkdownParser",
    # Tools
    "TOOL_AREAS",
    "DEFAULT_TOOL_AREAS",
    "load_agentic_tools",
    # LLM
    "DeepSeekPlanner",
    "DeepSeekSettings",
    "load_dotenv",
]
