"""
Yggdrasil 认知架构 —— 核心数据模型

统一节点模型：将 Skill、Memory、Knowledge 三种资产抽象为 TreeNode，
通过 NodeLink 维护显式/隐式/共现三种关联边。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(str, Enum):
    """节点类型 —— 树的隐喻映射"""

    ROOT = "root"          # 根节点 /
    DOMAIN = "domain"      # 领域节点，如 /database/
    SKILL = "skill"        # 可执行能力（枝）
    KNOWLEDGE = "knowledge"  # 领域知识（叶）
    MEMORY = "memory"      # 经验/反思（根）


class RelationType(str, Enum):
    """关联边类型"""

    EXPLICIT = "explicit"        # 显式结构关系（人工标注或系统确认）
    IMPLICIT = "implicit"        # 隐式语义关联（基于 embedding 相似度）
    COOCCURRENCE = "cooccurrence"  # 共现统计关联（运行时记录）


@dataclass
class TreeNode:
    """世界树统一节点"""

    id: str
    parent_id: Optional[str]
    domain: str
    node_type: NodeType
    title: str
    content: Optional[str] = None
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    health: float = 1.0
    branch_id: str = "main"
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # 运行时字段（不持久化到 MySQL）
    embedding: Optional[List[float]] = field(default=None, repr=False)
    children: List["TreeNode"] = field(default_factory=list, repr=False)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "TreeNode":
        """从 MySQL 查询结果行构建 TreeNode"""
        import json as _json
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = _json.loads(metadata)
        return cls(
            id=row["id"],
            parent_id=row.get("parent_id"),
            domain=row.get("domain", "/"),
            node_type=NodeType(row["node_type"]),
            title=row.get("title", ""),
            content=row.get("content"),
            summary=row.get("summary"),
            metadata=metadata or {},
            weight=float(row.get("weight", 1.0)),
            health=float(row.get("health", 1.0)),
            branch_id=row.get("branch_id", "main"),
            version=int(row.get("version", 1)),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )

    def to_text(self) -> str:
        """节点的文本表示（用于 embedding 和检索）"""
        parts = [self.title]
        if self.summary:
            parts.append(self.summary)
        elif self.content:
            parts.append(self.content[:500])
        return "\n".join(parts)


@dataclass
class NodeLink:
    """节点关联边"""

    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    label: Optional[str] = None
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "NodeLink":
        import json as _json
        metadata = row.get("metadata")
        if isinstance(metadata, str):
            metadata = _json.loads(metadata)
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=RelationType(row["relation_type"]),
            label=row.get("label"),
            weight=float(row.get("weight", 1.0)),
            metadata=metadata or {},
        )


@dataclass
class SubtreeResult:
    """子树检索结果"""

    anchor: TreeNode
    nodes: List[TreeNode]
    links: List[NodeLink]
    total_tokens_estimate: int = 0


@dataclass
class SandboxResult:
    """沙盒执行结果（Phase 2 启用）"""

    branch_id: str
    verdict: str  # "benign" | "harmful"
    reason: str
    new_nodes: List[TreeNode] = field(default_factory=list)
    weight_changes: Dict[str, float] = field(default_factory=dict)


@dataclass
class MigrationReport:
    """数据迁移报告"""

    skills_migrated: int = 0
    knowledge_migrated: int = 0
    memories_migrated: int = 0
    embeddings_generated: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.skills_migrated + self.knowledge_migrated + self.memories_migrated

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


__all__ = [
    "NodeType",
    "RelationType",
    "TreeNode",
    "NodeLink",
    "SubtreeResult",
    "SandboxResult",
    "MigrationReport",
]