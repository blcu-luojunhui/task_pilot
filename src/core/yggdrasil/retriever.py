"""
Yggdrasil 认知架构 —— 子树检索器

TreeRetriever 是整个 Yggdrasil 的核心 API，实现 PRD FR-4：
通过 intent embedding 检索最相关的锚点，沿树结构收集子树，
按 weight × relevance 排序剪枝，返回结构化上下文子树。
"""

import logging
from typing import Dict, List, Optional, Tuple

from .config import YggdrasilConfig
from .embedding import EmbeddingService
from .models import NodeType, SubtreeResult, TreeNode
from .store import TreeStore

logger = logging.getLogger("yggdrasil.retriever")


class TreeRetriever:
    """上下文子树检索器 —— Yggdrasil 核心 API"""

    def __init__(
        self,
        store: TreeStore,
        embedding: EmbeddingService,
        config: YggdrasilConfig,
    ):
        self.store = store
        self.embedding = embedding
        self.config = config

    async def retrieve_subtree(
        self,
        intent: str,
        max_tokens: Optional[int] = None,
        max_depth: Optional[int] = None,
        node_type_filter: Optional[List[NodeType]] = None,
    ) -> SubtreeResult:
        """
        根据意图检索最相关的上下文子树。

        工作流：
        1. intent → embedding 向量
        2. ChromaDB 向量检索 top-K 候选锚点
        3. 对每个候选锚点 BFS 收集子树
        4. 去重后按 weight × semantic_relevance 排序
        5. 贪心剪枝：累计 token 估算不超过 max_tokens

        Args:
            intent: 当前任务意图文本
            max_tokens: 子树最大 token 数，默认使用 config.retrieval_max_tokens
            max_depth: 子树最大深度，默认使用 config.retrieval_max_depth
            node_type_filter: 可选，限制检索的节点类型

        Returns:
            SubtreeResult: 包含锚点、节点列表、边列表、token 估算
        """
        max_tokens = max_tokens or self.config.retrieval_max_tokens
        max_depth = max_depth or self.config.retrieval_max_depth

        if not intent or not intent.strip():
            return SubtreeResult(
                anchor=TreeNode(
                    id="empty", parent_id=None, domain="/",
                    node_type=NodeType.ROOT, title="空检索",
                ),
                nodes=[],
                links=[],
                total_tokens_estimate=0,
            )

        # 1. 意图向量化
        query_embedding = await self.embedding.embed(intent)

        # 2. 向量检索锚点
        anchors = await self._find_anchors(query_embedding, node_type_filter)
        if not anchors:
            logger.debug("TreeRetriever: no anchors found for intent: %s", intent[:80])
            return SubtreeResult(
                anchor=TreeNode(
                    id="empty", parent_id=None, domain="/",
                    node_type=NodeType.ROOT, title="空检索",
                ),
                nodes=[],
                links=[],
                total_tokens_estimate=0,
            )

        # 3. 对每个锚点收集子树
        all_nodes: Dict[str, TreeNode] = {}
        node_scores: Dict[str, float] = {}
        for anchor_node, anchor_score in anchors:
            subtree_nodes = await self.store.get_subtree(anchor_node.id, max_depth)
            for node in subtree_nodes:
                if node.id not in all_nodes:
                    all_nodes[node.id] = node
                    node_scores[node.id] = anchor_score  # 初始分数 = 锚点相似度
                else:
                    # 同一节点出现在多个锚点的子树中，取最高分
                    node_scores[node.id] = max(node_scores[node.id], anchor_score)

        # 4. 按 weight × semantic_relevance 排序
        scored_nodes = self._rank_nodes(all_nodes, node_scores)

        # 5. 贪心剪枝
        pruned_nodes = self._prune_by_tokens(scored_nodes, max_tokens)

        total_estimate = sum(self.estimate_tokens(n) for n in pruned_nodes)

        logger.debug(
            "TreeRetriever: retrieved %d anchors → %d unique nodes → %d pruned (%d tokens)",
            len(anchors), len(all_nodes), len(pruned_nodes), total_estimate,
        )

        return SubtreeResult(
            anchor=anchors[0][0],
            nodes=pruned_nodes,
            links=[],  # Phase 1 暂不加载 edges
            total_tokens_estimate=total_estimate,
        )

    async def _find_anchors(
        self,
        query_embedding: List[float],
        node_type_filter: Optional[List[NodeType]] = None,
    ) -> List[Tuple[TreeNode, float]]:
        """向量检索候选锚点，返回 (node, score) 列表"""
        pairs = await self.embedding.search_similar(
            query_embedding,
            top_k=self.config.retrieval_top_k,
            min_health=self.config.health_retrieval_threshold,
        )

        anchors = []
        for node_id, score in pairs:
            node = await self.store.get_node(node_id)
            if node is None:
                continue
            if node_type_filter and node.node_type not in node_type_filter:
                continue
            # 过滤掉 weight 过低的节点（已枯萎）
            if node.weight < 0.1:
                continue
            anchors.append((node, score))

        return anchors

    def _rank_nodes(
        self,
        all_nodes: Dict[str, TreeNode],
        node_scores: Dict[str, float],
    ) -> List[Tuple[TreeNode, float]]:
        """按 weight × semantic_relevance 综合排序"""
        scored = []
        for node_id, node in all_nodes.items():
            relevance = node_scores.get(node_id, 0.0)
            combined = node.weight * relevance
            scored.append((node, combined))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _prune_by_tokens(
        self,
        scored_nodes: List[Tuple[TreeNode, float]],
        max_tokens: int,
    ) -> List[TreeNode]:
        """贪心剪枝：按综合分数从高到低取，累计 token 不超过 max_tokens"""
        result = []
        total = 0
        for node, _score in scored_nodes:
            est = self.estimate_tokens(node)
            if total + est > max_tokens:
                break
            result.append(node)
            total += est
        return result

    def estimate_tokens(self, node: TreeNode) -> int:
        """估算节点内容的 token 数（摘要优先）"""
        text = node.summary or node.content or ""
        # 粗略估算：中文约 1.5 char/token，英文约 4 char/token，取折中 3
        return max(1, len(text) // 3)


__all__ = ["TreeRetriever"]