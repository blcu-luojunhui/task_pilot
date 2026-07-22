"""
Yggdrasil 认知架构 —— 向量嵌入服务

EmbeddingService 负责：
- 调用 LLM embedding API 生成文本向量
- ChromaDB 向量索引的增删改查
- 语义相似度检索
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import YggdrasilConfig
from .models import NodeType, TreeNode

logger = logging.getLogger("yggdrasil.embedding")


class EmbeddingService:
    """向量嵌入服务 —— 抽象 embedding 生成与向量存储"""

    def __init__(self, config: YggdrasilConfig, llm_provider: Any = None):
        self.config = config
        self.llm_provider = llm_provider
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[Any] = None

    # ================================================================
    # ChromaDB 生命周期
    # ================================================================

    async def initialize(self) -> None:
        """初始化 ChromaDB 客户端和 collection"""
        self._client = chromadb.PersistentClient(
            path=self.config.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        try:
            self._collection = self._client.get_collection(
                name=self.config.chroma_collection_name,
            )
            logger.info(
                "ChromaDB collection '%s' loaded: %d documents",
                self.config.chroma_collection_name,
                self._collection.count(),
            )
        except Exception:
            self._collection = self._client.create_collection(
                name=self.config.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "ChromaDB collection '%s' created",
                self.config.chroma_collection_name,
            )

    async def close(self) -> None:
        """关闭 ChromaDB 客户端"""
        if self._client:
            # ChromaDB PersistentClient 不需要显式关闭
            self._client = None
            self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            raise RuntimeError("EmbeddingService not initialized. Call initialize() first.")
        return self._collection

    # ================================================================
    # Embedding 生成
    # ================================================================

    async def embed(self, text: str) -> List[float]:
        """生成单个文本的 embedding 向量"""
        if not text or not text.strip():
            return [0.0] * self.config.embedding_dimensions

        # 优先使用 LLM provider 的 embedding 能力
        if self.llm_provider and hasattr(self.llm_provider, "embed"):
            try:
                return await self.llm_provider.embed(text)
            except Exception as e:
                logger.warning("LLM embedding failed, falling back to mock: %s", e)

        return self._mock_embed(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成 embedding 向量"""
        embeddings = []
        batch_size = self.config.embedding_batch_size
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            if self.llm_provider and hasattr(self.llm_provider, "embed_batch"):
                try:
                    batch_embeddings = await self.llm_provider.embed_batch(batch)
                    embeddings.extend(batch_embeddings)
                    continue
                except Exception as e:
                    logger.warning("LLM batch embedding failed: %s", e)
            for text in batch:
                embeddings.append(self._mock_embed(text))
        return embeddings

    def _mock_embed(self, text: str) -> List[float]:
        """Mock embedding：基于文本 hash 生成伪向量（开发/测试用）"""
        import hashlib

        h = hashlib.sha256(text.encode("utf-8")).digest()
        dims = self.config.embedding_dimensions
        # 从 hash 中循环取字节生成 dims 维向量
        vec = []
        for i in range(dims):
            byte_val = h[i % len(h)] / 255.0
            vec.append(byte_val * 2 - 1)  # 映射到 [-1, 1]
        # L2 归一化
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    # ================================================================
    # ChromaDB 索引操作
    # ================================================================

    async def index_node(self, node: TreeNode) -> None:
        """将节点索引到 ChromaDB"""
        text = node.to_text()
        embedding = await self.embed(text)
        node.embedding = embedding

        self.collection.add(
            ids=[node.id],
            embeddings=[embedding],
            metadatas=[{
                "node_type": node.node_type.value,
                "title": node.title,
                "domain": node.domain,
                "weight": node.weight,
                "health": node.health,
            }],
            documents=[text],
        )
        logger.debug("ChromaDB: indexed node %s", node.id)

    async def deindex_node(self, node_id: str) -> None:
        """从 ChromaDB 删除节点索引"""
        self.collection.delete(ids=[node_id])
        logger.debug("ChromaDB: deindexed node %s", node_id)

    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        node_type: Optional[NodeType] = None,
        min_health: float = 0.3,
    ) -> List[Tuple[str, float]]:
        """
        向量相似度检索。

        Returns:
            [(node_id, similarity_score), ...] 按相似度降序
        """
        where_filter = None
        if node_type:
            where_filter = {"node_type": node_type.value}

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
        )

        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        # ChromaDB 返回的是 distance（cosine distance），转换为 similarity
        pairs = []
        for node_id, distance in zip(ids, distances):
            similarity = 1.0 - distance  # cosine similarity
            pairs.append((node_id, similarity))

        return pairs

    async def rebuild_index(self, nodes: List[TreeNode]) -> int:
        """从节点列表全量重建 ChromaDB 索引"""
        # 删除旧 collection，重建
        if self._client:
            try:
                self._client.delete_collection(self.config.chroma_collection_name)
            except Exception:
                pass
            self._collection = self._client.create_collection(
                name=self.config.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )

        indexed = 0
        batch_size = self.config.embedding_batch_size
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            texts = [n.to_text() for n in batch]
            embeddings = await self.embed_batch(texts)

            self.collection.add(
                ids=[n.id for n in batch],
                embeddings=embeddings,
                metadatas=[{
                    "node_type": n.node_type.value,
                    "title": n.title,
                    "domain": n.domain,
                    "weight": n.weight,
                    "health": n.health,
                } for n in batch],
                documents=texts,
            )
            indexed += len(batch)
            logger.debug("ChromaDB rebuild: indexed %d/%d nodes", indexed, len(nodes))

        logger.info("ChromaDB rebuild complete: %d nodes indexed", indexed)
        return indexed


__all__ = ["EmbeddingService"]