"""
Evaluator - Benchmark 和评估
"""

import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class EvaluationMetric:
    """评估指标"""

    name: str
    value: float
    unit: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """评估结果"""

    task_id: str
    metrics: List[EvaluationMetric]
    success: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


class Evaluator:
    """
    Agent 评估器

    用于：
    1. Benchmark 测试
    2. 性能评估
    3. 质量评估
    """

    def __init__(self):
        self.results: List[EvaluationResult] = []

    async def evaluate(
        self, agent, test_cases: List[Dict[str, Any]], metrics: Optional[List[str]] = None
    ) -> List[EvaluationResult]:
        """
        评估 Agent

        Args:
            agent: Agent 实例
            test_cases: 测试用例列表 (每个包含 "goal" 和可选 "expected" 字段)
            metrics: 要评估的指标名称列表 (默认: ["success", "steps", "latency", "tool_calls"])

        Returns:
            评估结果列表
        """
        results = []

        for test_case in test_cases:
            result = await self._evaluate_single(agent, test_case, metrics)
            results.append(result)
            self.results.append(result)

        return results

    async def _evaluate_single(
        self, agent, test_case: Dict[str, Any], metrics: Optional[List[str]]
    ) -> EvaluationResult:
        """评估单个测试用例"""
        task_id = test_case.get("id", test_case.get("goal", "unknown")[:60])
        goal = test_case.get("goal", "")
        expected = test_case.get("expected")
        metric_names = metrics or ["success", "steps", "latency", "tool_calls"]

        started = time.monotonic()
        try:
            loop_result = await agent.run(goal)
            elapsed = time.monotonic() - started

            eval_metrics = []
            for name in metric_names:
                if name == "success":
                    eval_metrics.append(
                        EvaluationMetric(name="success", value=1.0 if loop_result.success else 0.0)
                    )
                elif name == "steps":
                    eval_metrics.append(
                        EvaluationMetric(
                            name="steps", value=float(loop_result.total_steps), unit="steps"
                        )
                    )
                elif name == "latency":
                    eval_metrics.append(
                        EvaluationMetric(name="latency", value=elapsed, unit="s")
                    )
                elif name == "tool_calls":
                    eval_metrics.append(
                        EvaluationMetric(
                            name="tool_calls",
                            value=float(loop_result.tool_calls_count),
                            unit="calls",
                        )
                    )

            # 检查预期答案（简单子串匹配）
            success = loop_result.success
            if expected and loop_result.final_answer:
                match = expected.lower() in loop_result.final_answer.lower()
                eval_metrics.append(EvaluationMetric(name="expected_match", value=1.0 if match else 0.0))
                success = success and match

            return EvaluationResult(
                task_id=task_id,
                metrics=eval_metrics,
                success=success,
                metadata={"goal": goal, "trace_id": loop_result.trace_id},
            )
        except Exception as e:
            elapsed = time.monotonic() - started
            return EvaluationResult(
                task_id=task_id,
                metrics=[
                    EvaluationMetric(name="success", value=0.0),
                    EvaluationMetric(name="latency", value=elapsed, unit="s"),
                    EvaluationMetric(name="error", value=1.0, metadata={"error": str(e)}),
                ],
                success=False,
                metadata={"goal": goal, "error": str(e)},
            )


__all__ = ["Evaluator", "EvaluationResult", "EvaluationMetric"]
