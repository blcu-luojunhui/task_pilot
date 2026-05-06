"""
Minimal goal-driven agent demo.

Run:
    python examples/minimal_goal_agent.py

Or pass another goal:
    python examples/minimal_goal_agent.py "帮我解释一下：三重积分的理解和应用"
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.agents.executor import AgentLoopRunner
from src.core.agents.skills import Skill, SkillExecutor, SkillRegistry


DEFAULT_GOAL = "帮我解释一下：三重积分的理解和应用"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


async def explain_math_concept(ctx, concept: str, goal: str) -> str:
    """A small executable skill that explains one math concept."""
    if "三重积分" not in concept:
        return f"我目前只内置了三重积分的最小解释能力，收到的概念是：{concept}"

    return (
        "三重积分可以理解为“在三维空间里累加很多很小的量”。\n\n"
        "1. 直观理解\n"
        "单积分是在一条线上累加，二重积分是在一个平面区域上累加，"
        "三重积分则是在一个空间区域内累加。可以把一个立体区域切成很多小盒子，"
        "每个小盒子的体积是 dV，如果某个函数 f(x, y, z) 表示这个位置的密度、温度、"
        "电荷密度或其他局部量，那么 f(x, y, z)dV 就表示这个小盒子的贡献。"
        "把所有小盒子的贡献加起来，就是三重积分。\n\n"
        "2. 典型形式\n"
        "∭_D f(x, y, z) dV，其中 D 是三维空间中的积分区域。"
        "如果 f(x, y, z)=1，那么积分结果就是区域 D 的体积。"
        "如果 f 表示密度，那么积分结果就是总质量。\n\n"
        "3. 常见应用\n"
        "- 计算立体体积\n"
        "- 根据密度函数计算物体质量\n"
        "- 计算质心、转动惯量\n"
        "- 计算三维区域中的电荷量、热量或概率\n\n"
        "4. 学习抓手\n"
        "先问三个问题：区域 D 是什么形状？被累加的量 f 是什么？"
        "用直角坐标、柱坐标还是球坐标描述更简单？"
    )


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(
        Skill.executable(
            name="explain_math_concept",
            description="根据目标解释一个数学概念",
            handler=explain_math_concept,
            parameters={
                "concept": {
                    "type": "string",
                    "description": "要解释的数学概念",
                    "required": True,
                },
                "goal": {
                    "type": "string",
                    "description": "用户的原始目标",
                    "required": True,
                },
            },
            dependencies=[],
            domain="math",
            tags=["education", "math"],
        )
    )
    return registry


@dataclass
class GoalDrivenPlanner:
    """
    A minimal deterministic planner.

    In production this role is normally played by an LLM adapter. Here it is
    intentionally small so the agent loop can run without external services.
    """

    goal: str

    async def __call__(self, messages: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
        tool_result = self._latest_tool_result(messages, "explain_math_concept")
        if tool_result:
            return {
                "role": "assistant",
                "content": f"我已经根据目标整理好了：\n\n{tool_result}",
            }

        concept = self._extract_concept()
        return {
            "role": "assistant",
            "content": f"我需要先解释核心概念：{concept}",
            "tool_calls": [
                {
                    "id": "call_explain_math",
                    "name": "explain_math_concept",
                    "arguments": {
                        "concept": concept,
                        "goal": self.goal,
                    },
                }
            ],
        }

    def _extract_concept(self) -> str:
        if "：" in self.goal:
            return self.goal.split("：", 1)[1].strip()
        if ":" in self.goal:
            return self.goal.split(":", 1)[1].strip()
        return self.goal.strip()

    def _latest_tool_result(
        self,
        messages: List[Dict[str, Any]],
        tool_name: str,
    ) -> str:
        for message in reversed(messages):
            if message.get("role") == "tool" and message.get("name") == tool_name:
                return message.get("content", "")
        return ""


async def run_agent(goal: str) -> str:
    registry = build_registry()
    runner = AgentLoopRunner(
        planner=GoalDrivenPlanner(goal),
        registry=registry,
        executor=SkillExecutor(),
        max_steps=3,
    )
    result = await runner.run(
        goal=goal,
        messages=[{"role": "user", "content": goal}],
    )

    if not result.success:
        return f"Agent stopped: {result.stop_reason.value}"
    return result.final_answer or ""


async def main() -> None:
    configure_logging()
    goal = " ".join(sys.argv[1:]).strip() or DEFAULT_GOAL
    answer = await run_agent(goal)
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
