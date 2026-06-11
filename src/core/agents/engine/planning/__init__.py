"""Planning 模块 — 可插拔的 Agent 决策策略"""

from .strategy import DecisionStrategy, StepOutput, StrategyContext
from .react import ReActStrategy
from .plan_execute import PlanExecuteStrategy
from .reflexion import ReflexionStrategy

STRATEGY_REGISTRY = {
    "react": ReActStrategy,
    "plan_execute": PlanExecuteStrategy,
    "reflexion": ReflexionStrategy,
}


def resolve_strategy(name: str):
    """根据名称解析策略类。非法名称抛出 ValueError。"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown strategy '{name}'. Supported: {list(STRATEGY_REGISTRY.keys())}"
        )
    return STRATEGY_REGISTRY[name]()


__all__ = [
    "DecisionStrategy",
    "StepOutput",
    "StrategyContext",
    "ReActStrategy",
    "PlanExecuteStrategy",
    "ReflexionStrategy",
    "STRATEGY_REGISTRY",
    "resolve_strategy",
]
