"""
Yggdrasil 认知架构 —— 持久化存储层

TreeStore 负责 tree_node 和 node_links 的 MySQL CRUD、DAG 约束检查、
领域骨架初始化。
"""

import json
import logging
import uuid
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from src.infra.database import AsyncMySQLPool

from .config import YggdrasilConfig
from .models import NodeLink, NodeType, RelationType, TreeNode

logger = logging.getLogger("yggdrasil.store")

# 预设领域骨架
_DEFAULT_DOMAINS = [
    "database",
    "http",
    "task",
    "auth",
    "observability",
]


class TreeStore:
    """世界树持久化存储"""

    def __init__(self, db: AsyncMySQLPool, config: YggdrasilConfig):
        self.db = db
        self.config = config

    # ================================================================
    # 节点 CRUD
    # ================================================================

    async def create_node(self, node: TreeNode) -> str:
        """创建节点，返回 node.id"""
        await self.db.async_save(
            """
            INSERT INTO tree_node (id, parent_id, domain, node_type, title, content,
                                   summary, metadata, weight, health, branch_id, version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                node.id,
                node.parent_id,
                node.domain,
                node.node_type.value,
                node.title,
                node.content,
                node.summary,
                json.dumps(node.metadata, ensure_ascii=False) if node.metadata else None,
                node.weight,
                node.health,
                node.branch_id,
                node.version,
            ),
        )
        logger.debug("TreeStore: created node %s (%s)", node.id, node.node_type.value)
        return node.id

    async def get_node(self, node_id: str) -> Optional[TreeNode]:
        """按 ID 获取节点"""
        rows = await self.db.async_fetch(
            "SELECT * FROM tree_node WHERE id = %s",
            (node_id,),
        )
        if not rows:
            return None
        return TreeNode.from_db_row(rows[0])

    async def update_node(self, node_id: str, **fields) -> None:
        """按字段更新节点"""
        if not fields:
            return
        allowed = {
            "parent_id", "domain", "title", "content", "summary",
            "metadata", "weight", "health", "branch_id",
        }
        set_parts = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            if key == "metadata" and isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            set_parts.append(f"{key} = %s")
            values.append(value)
        if not set_parts:
            return
        set_parts.append("version = version + 1")
        values.append(node_id)
        sql = f"UPDATE tree_node SET {', '.join(set_parts)} WHERE id = %s"
        await self.db.async_save(sql, tuple(values))

    async def delete_node(self, node_id: str) -> None:
        """删除节点（级联删除子节点）"""
        children = await self.list_children(node_id)
        for child in children:
            await self.delete_node(child.id)
        await self.db.async_save(
            "DELETE FROM node_links WHERE source_id = %s OR target_id = %s",
            (node_id, node_id),
        )
        await self.db.async_save(
            "DELETE FROM tree_node WHERE id = %s",
            (node_id,),
        )

    async def list_children(
        self, parent_id: str, node_type: Optional[NodeType] = None,
    ) -> List[TreeNode]:
        """列出子节点"""
        if node_type:
            rows = await self.db.async_fetch(
                "SELECT * FROM tree_node WHERE parent_id = %s AND node_type = %s ORDER BY weight DESC",
                (parent_id, node_type.value),
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM tree_node WHERE parent_id = %s ORDER BY weight DESC",
                (parent_id,),
            )
        return [TreeNode.from_db_row(r) for r in rows]

    async def list_by_domain(
        self, domain: str, node_type: Optional[NodeType] = None,
    ) -> List[TreeNode]:
        """按领域路径列出节点"""
        if node_type:
            rows = await self.db.async_fetch(
                "SELECT * FROM tree_node WHERE domain = %s AND node_type = %s ORDER BY weight DESC",
                (domain, node_type.value),
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM tree_node WHERE domain = %s ORDER BY weight DESC",
                (domain,),
            )
        return [TreeNode.from_db_row(r) for r in rows]

    async def search_by_title(self, keyword: str, limit: int = 20) -> List[TreeNode]:
        """按标题模糊搜索"""
        rows = await self.db.async_fetch(
            "SELECT * FROM tree_node WHERE title LIKE %s ORDER BY weight DESC LIMIT %s",
            (f"%{keyword}%", limit),
        )
        return [TreeNode.from_db_row(r) for r in rows]

    async def count_nodes(self, node_type: Optional[NodeType] = None) -> int:
        """统计节点总数"""
        if node_type:
            rows = await self.db.async_fetch(
                "SELECT COUNT(*) AS cnt FROM tree_node WHERE node_type = %s",
                (node_type.value,),
            )
        else:
            rows = await self.db.async_fetch("SELECT COUNT(*) AS cnt FROM tree_node")
        return rows[0]["cnt"] if rows else 0

    async def get_all_nodes(self) -> List[TreeNode]:
        """获取所有节点（用于全量索引重建）"""
        rows = await self.db.async_fetch("SELECT * FROM tree_node ORDER BY id")
        return [TreeNode.from_db_row(r) for r in rows]

    # ================================================================
    # 链接管理
    # ================================================================

    async def add_link(self, link: NodeLink) -> str:
        """添加关联边，自动检测环路"""
        if link.relation_type == RelationType.EXPLICIT:
            would_cycle = await self.would_create_cycle(link.source_id, link.target_id)
            if would_cycle:
                raise ValueError(
                    f"Adding link {link.source_id} → {link.target_id} would create a cycle"
                )
        await self.db.async_save(
            """
            INSERT INTO node_links (id, source_id, target_id, relation_type, label, weight, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE weight = weight + VALUES(weight), updated_at = CURRENT_TIMESTAMP(3)
            """,
            (
                link.id,
                link.source_id,
                link.target_id,
                link.relation_type.value,
                link.label,
                link.weight,
                json.dumps(link.metadata, ensure_ascii=False) if link.metadata else None,
            ),
        )
        return link.id

    async def remove_link(self, link_id: str) -> None:
        """删除关联边"""
        await self.db.async_save(
            "DELETE FROM node_links WHERE id = %s",
            (link_id,),
        )

    async def get_links(
        self, node_id: str, relation_type: Optional[RelationType] = None,
    ) -> List[NodeLink]:
        """获取节点的所有关联边"""
        if relation_type:
            rows = await self.db.async_fetch(
                "SELECT * FROM node_links WHERE (source_id = %s OR target_id = %s) AND relation_type = %s",
                (node_id, node_id, relation_type.value),
            )
        else:
            rows = await self.db.async_fetch(
                "SELECT * FROM node_links WHERE source_id = %s OR target_id = %s",
                (node_id, node_id),
            )
        return [NodeLink.from_db_row(r) for r in rows]

    async def would_create_cycle(self, source_id: str, target_id: str) -> bool:
        """
        检测从 source → target 加边是否会产生环。

        算法：从 target 出发做 BFS，沿 parent_id（向上）和 explicit links（双向）
        遍历，如果可达 source，则加边会成环。
        """
        visited: set = set()
        queue: deque = deque([target_id])

        while queue:
            current = queue.popleft()
            if current == source_id:
                return True
            if current in visited:
                continue
            visited.add(current)

            # 沿 parent_id 向上
            node = await self.get_node(current)
            if node and node.parent_id and node.parent_id not in visited:
                queue.append(node.parent_id)

            # 沿 explicit links 双向遍历
            links = await self.get_links(current, RelationType.EXPLICIT)
            for link in links:
                neighbor = link.target_id if link.source_id == current else link.source_id
                if neighbor not in visited:
                    queue.append(neighbor)

        return False

    # ================================================================
    # 骨架初始化
    # ================================================================

    async def ensure_skeleton(self) -> None:
        """确保树的骨架存在（首次启动时调用）"""
        root = await self.get_node("root")
        if root is None:
            logger.info("Yggdrasil: initializing tree skeleton...")
            await self._create_root()
            for domain_name in _DEFAULT_DOMAINS:
                await self._create_domain_subtree(domain_name)
            logger.info("Yggdrasil: tree skeleton initialized with %d domains", len(_DEFAULT_DOMAINS))
        else:
            logger.debug("Yggdrasil: tree skeleton already exists")

    async def _create_root(self) -> TreeNode:
        """创建根节点"""
        root = TreeNode(
            id="root",
            parent_id=None,
            domain="/",
            node_type=NodeType.ROOT,
            title="世界树根节点",
            summary="Yggdrasil 认知架构的根节点，所有领域子树从此分叉",
        )
        await self.create_node(root)
        return root

    async def _create_domain_subtree(self, domain_name: str) -> None:
        """创建领域子树：/domain/ → _skills, _knowledge, _memories"""
        domain_node = TreeNode(
            id=f"domain-{domain_name}",
            parent_id="root",
            domain=f"/{domain_name}/",
            node_type=NodeType.DOMAIN,
            title=f"{domain_name} 领域",
        )
        await self.create_node(domain_node)

        for subspace in ("_skills", "_knowledge", "_memories"):
            subspace_node = TreeNode(
                id=f"domain-{domain_name}-{subspace}",
                parent_id=domain_node.id,
                domain=f"/{domain_name}/{subspace}/",
                node_type=NodeType.DOMAIN,
                title=f"{domain_name} {subspace.lstrip('_')}",
            )
            await self.create_node(subspace_node)

    async def get_or_create_domain(self, domain_path: str) -> TreeNode:
        """获取或创建领域节点"""
        domain_path = domain_path.rstrip("/")
        if not domain_path.startswith("/"):
            domain_path = f"/{domain_path}"

        node_id = f"domain-{domain_path.strip('/').replace('/', '-')}"
        existing = await self.get_node(node_id)
        if existing:
            return existing

        # 确保父领域存在
        parent_path = "/".join(domain_path.split("/")[:-1]) or "/"
        if parent_path != "/":
            parent = await self.get_or_create_domain(parent_path)
            parent_id = parent.id
        else:
            parent_id = "root"

        node = TreeNode(
            id=node_id,
            parent_id=parent_id,
            domain=f"{domain_path}/",
            node_type=NodeType.DOMAIN,
            title=domain_path.strip("/").split("/")[-1],
        )
        await self.create_node(node)
        return node

    # ================================================================
    # 批量操作
    # ================================================================

    async def bulk_create_nodes(self, nodes: List[TreeNode]) -> List[str]:
        """批量创建节点"""
        ids = []
        for node in nodes:
            nid = await self.create_node(node)
            ids.append(nid)
        return ids

    async def get_subtree(
        self, root_id: str, max_depth: int = 3,
    ) -> List[TreeNode]:
        """从 root_id 出发 BFS 收集子树"""
        result: List[TreeNode] = []
        visited: set = set()
        queue: deque = deque([(root_id, 0)])

        while queue:
            node_id, depth = queue.popleft()
            if node_id in visited or depth > max_depth:
                continue
            visited.add(node_id)

            node = await self.get_node(node_id)
            if node is None:
                continue
            result.append(node)

            if depth < max_depth:
                children = await self.list_children(node_id)
                for child in children:
                    if child.id not in visited:
                        queue.append((child.id, depth + 1))

        return result

    @staticmethod
    def new_id(prefix: str = "node") -> str:
        """生成唯一节点 ID"""
        suffix = uuid.uuid4().hex[:8]
        return f"{prefix}-{suffix}"


__all__ = ["TreeStore", "_DEFAULT_DOMAINS"]