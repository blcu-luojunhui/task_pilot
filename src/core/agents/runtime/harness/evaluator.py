"""
Evaluator - Benchmark 和评估 (OPT-11 落地)
"""

import json
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
    3. 质量评估 (LLM-as-judge)
    """

    def __init__(self, judge_provider=None):
        self.results: List[EvaluationResult] = []
        self.judge_provider = judge_provider

    async def evaluate(
        self, agent, test_cases: List[Dict[str, Any]], metrics: Optional[List[str]] = None
    ) -> List[EvaluationResult]:
        """评估 Agent"""
        self.results.clear()
        for test_case in test_cases:
            result = await self._evaluate_single(agent, test_case, metrics)
            self.results.append(result)
        return list(self.results)

    async def _evaluate_single(
        self, agent, test_case: Dict[str, Any], metrics: Optional[List[str]]
    ) -> EvaluationResult:
        """评估单个测试用例"""
        task_id = test_case.get("id", test_case.get("goal", "")[:60])
        goal = test_case.get("goal", "")
        expected = test_case.get("expected")
        metric_names = metrics or ["success", "steps", "latency", "tool_calls", "token_usage"]

        started = time.monotonic()
        try:
            loop_result = await agent.run(goal)
            elapsed = time.monotonic() - started

            eval_metrics: List[EvaluationMetric] = []
            for name in metric_names:
                if name == "success":
                    eval_metrics.append(
                        EvaluationMetric(name="success", value=1.0 if loop_result.success else 0.0)
                    )
                elif name == "steps":
                    eval_metrics.append(
                        EvaluationMetric(name="steps", value=float(loop_result.total_steps), unit="steps")
                    )
                elif name == "latency":
                    eval_metrics.append(EvaluationMetric(name="latency", value=elapsed, unit="s"))
                elif name == "tool_calls":
                    eval_metrics.append(
                        EvaluationMetric(
                            name="tool_calls", value=float(loop_result.tool_calls_count), unit="calls"
                        )
                    )
                elif name == "token_usage":
                    eval_metrics.append(
                        EvaluationMetric(
                            name="token_usage",
                            value=float(loop_result.token_usage.get("total", 0)),
                            unit="tokens",
                        )
                    )

            success = loop_result.success

            # 期望答案匹配（子串）
            if expected and loop_result.final_answer:
                match = expected.lower() in loop_result.final_answer.lower()
                eval_metrics.append(
                    EvaluationMetric(name="expected_match", value=1.0 if match else 0.0)
                )
                success = success and match

            # LLM-as-judge
            if self.judge_provider and loop_result.final_answer:
                try:
                    score = await self._judge(goal, loop_result.final_answer or "")
                    eval_metrics.append(EvaluationMetric(name="judge_score", value=score))
                except Exception:
                    pass

            return EvaluationResult(
                task_id=task_id,
                metrics=eval_metrics,
                success=success,
                metadata={"goal": goal, "trace_id": loop_result.trace_id},
            )
        except Exception as e:
            return EvaluationResult(
                task_id=task_id,
                metrics=[
                    EvaluationMetric(name="success", value=0.0),
                    EvaluationMetric(name="latency", value=time.monotonic() - started, unit="s"),
                    EvaluationMetric(name="error", value=1.0, metadata={"error": str(e)}),
                ],
                success=False,
                metadata={"goal": goal, "error": str(e)},
            )

    async def _judge(self, goal: str, answer: str) -> float:
        """LLM-as-judge 打分 0.0-1.0"""
        from src.core.agents.capabilities.llm.base import LLMMessage

        prompt = (
            f"Rate the following answer on a scale of 0.0 to 1.0 based on how well "
            f"it addresses the goal.\n\nGoal: {goal}\n\nAnswer: {answer[:2000]}\n\n"
            f"Output ONLY a number between 0.0 and 1.0."
        )
        response = await self.judge_provider.chat(
            messages=[LLMMessage(role="user", content=prompt)],
            temperature=0.0,
            max_tokens=10,
        )
        try:
            return max(0.0, min(1.0, float(response.content.strip())))
        except ValueError:
            return 0.5

    def summarize(self, results: Optional[List[EvaluationResult]] = None) -> str:
        """生成评估汇总报告"""
        data = results or self.results
        if not data:
            return "No evaluation results."

        total = len(data)
        success_count = sum(1 for r in data if r.success)
        success_rate = success_count / total * 100 if total > 0 else 0

        lines = [
            f"Evaluation Summary ({total} cases)",
            f"  Success Rate: {success_count}/{total} ({success_rate:.1f}%)",
        ]
        for name in ("latency", "steps", "tool_calls", "token_usage", "judge_score"):
            values = []
            for r in data:
                for m in r.metrics:
                    if m.name == name:
                        values.append(m.value)
            if values:
                avg = sum(values) / len(values)
                unit = next(
                    (m.unit for r in data for m in r.metrics if m.name == name), ""
                )
                unit_str = f" {unit}" if unit else ""
                lines.append(f"  Avg {name}: {avg:.2f}{unit_str}")

        failed = [r for r in data if not r.success]
        if failed:
            lines.append(f"  Failed cases ({len(failed)}):")
            for f in failed:
                err = f.metadata.get("error", "unknown")
                lines.append(f"    - {f.task_id}: {err[:80]}")
        return "\n".join(lines)

    def to_json(
        self, filepath: str, results: Optional[List[EvaluationResult]] = None
    ) -> None:
        """持久化评测结果为 JSON"""
        data = results or self.results
        report = {
            "summary": self.summarize(data),
            "cases": [
                {
                    "task_id": r.task_id,
                    "success": r.success,
                    "metrics": [
                        {"name": m.name, "value": m.value, "unit": m.unit} for m in r.metrics
                    ],
                    "metadata": r.metadata,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in data
            ],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


__all__ = ["Evaluator", "EvaluationResult", "EvaluationMetric"]
