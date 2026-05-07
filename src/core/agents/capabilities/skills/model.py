"""
Skill 数据模型

纯数据模型，不包含执行和序列化逻辑
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import uuid


class SkillType(str, Enum):
    EXECUTABLE = "executable"
    KNOWLEDGE = "knowledge"


class RiskLevel(str, Enum):
    """工具风险等级"""

    READ = "read"  # 只读操作，无副作用
    WRITE = "write"  # 写操作，可逆
    DESTRUCTIVE = "destructive"  # 危险操作，不可逆


@dataclass
class Skill:
    """
    技能数据模型

    职责：只承载数据，不包含执行/序列化逻辑
    执行由 SkillExecutor 负责，序列化由 ToolSpecAdapter 负责
    """

    skill_id: str
    name: str
    description: str
    skill_type: SkillType
    scope: str = "agent:*"
    domain: str = "general"
    tags: List[str] = field(default_factory=list)

    # 层次结构
    parent_id: Optional[str] = None

    # 可执行技能
    handler: Optional[Callable] = field(default=None, repr=False)
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.READ
    examples: List[Dict[str, Any]] = field(default_factory=list)

    # 知识型技能
    content: Optional[str] = None
    guidelines: List[str] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)

    # 元数据
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # PLACEHOLDER_MODEL_METHODS

    @classmethod
    def executable(
        cls,
        name: str,
        description: str,
        handler: Callable,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        dependencies: Optional[List[str]] = None,
        scope: str = "agent:*",
        domain: str = "general",
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
        risk_level: RiskLevel = RiskLevel.READ,
        examples: Optional[List[Dict[str, Any]]] = None,
    ) -> "Skill":
        """创建可执行技能"""
        now = datetime.now()
        return cls(
            skill_id=str(uuid.uuid4()),
            name=name,
            description=description,
            skill_type=SkillType.EXECUTABLE,
            scope=scope,
            domain=domain,
            tags=tags or [],
            parent_id=parent_id,
            handler=handler,
            parameters=parameters or {},
            dependencies=dependencies or [],
            risk_level=risk_level,
            examples=examples or [],
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def knowledge(
        cls,
        name: str,
        description: str,
        scope: str = "agent:*",
        domain: str = "general",
        tags: Optional[List[str]] = None,
        content: Optional[str] = None,
        guidelines: Optional[List[str]] = None,
        derived_from: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
    ) -> "Skill":
        """创建知识型技能"""
        now = datetime.now()
        return cls(
            skill_id=str(uuid.uuid4()),
            name=name,
            description=description,
            skill_type=SkillType.KNOWLEDGE,
            scope=scope,
            domain=domain,
            tags=tags or [],
            parent_id=parent_id,
            content=content,
            guidelines=guidelines or [],
            derived_from=derived_from or [],
            created_at=now,
            updated_at=now,
        )

    # 向后兼容别名
    create_executable = executable
    create_knowledge = knowledge

    @property
    def is_executable(self) -> bool:
        return self.skill_type == SkillType.EXECUTABLE

    @property
    def is_knowledge(self) -> bool:
        return self.skill_type == SkillType.KNOWLEDGE

    def to_prompt_text(self) -> str:
        """转换为可注入 Prompt 的文本（知识型技能）"""
        if self.content:
            return self.content.strip()

        lines = [f"### {self.name}", "", self.description]
        if self.guidelines:
            lines.append("")
            for g in self.guidelines:
                lines.append(f"- {g}")
        return "\n".join(lines)


__all__ = ["Skill", "SkillType", "RiskLevel"]
