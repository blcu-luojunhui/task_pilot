"""
Yggdrasil 认知架构 —— 配置

所有可配置参数集中管理，通过环境变量 YGGDRASIL_* 覆盖。
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class YggdrasilConfig(BaseSettings):
    """世界树全局配置"""

    # ============ 全局开关 ============
    enabled: bool = Field(default=False, description="是否启用 Yggdrasil 子树检索（Phase 1 默认关闭）")

    # ============ ChromaDB ============
    chroma_persist_dir: str = Field(
        default="./data/yggdrasil_chroma",
        description="ChromaDB 持久化目录",
    )
    chroma_collection_name: str = Field(
        default="tree_nodes",
        description="ChromaDB collection 名称",
    )

    # ============ Embedding ============
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding 模型名称",
    )
    embedding_dimensions: int = Field(
        default=1536,
        description="Embedding 向量维度",
    )
    embedding_batch_size: int = Field(
        default=100,
        description="批量 embedding 请求大小",
    )

    # ============ 检索 ============
    retrieval_top_k: int = Field(
        default=20,
        description="向量检索返回的候选锚点数",
    )
    retrieval_max_depth: int = Field(
        default=3,
        description="子树收集最大深度",
    )
    retrieval_max_tokens: int = Field(
        default=8000,
        description="子树上下文最大 token 数",
    )

    # ============ 生长（Phase 2 启用） ============
    weight_success_bonus: float = Field(
        default=1.0,
        description="Skill 成功调用权重奖励",
    )
    weight_positive_bonus: float = Field(
        default=2.0,
        description="Skill 产出正向结果权重奖励",
    )
    weight_decay_rate: float = Field(
        default=0.95,
        description="每次时间衰减的乘数因子",
    )
    weight_decay_interval_days: int = Field(
        default=7,
        description="时间衰减执行间隔（天）",
    )

    # ============ 健康（Phase 3 启用） ============
    health_contagion_decay: float = Field(
        default=0.5,
        description="污染传播衰减因子",
    )
    health_retrieval_threshold: float = Field(
        default=0.3,
        description="检索时过滤健康值低于此阈值的节点",
    )

    # ============ 沙盒（Phase 2 启用） ============
    sandbox_max_parallel: int = Field(
        default=3,
        description="最大并行沙盒数",
    )

    model_config = SettingsConfigDict(
        env_prefix="YGGDRASIL_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


__all__ = ["YggdrasilConfig"]