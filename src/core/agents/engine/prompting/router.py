"""Task router implementation — goal decomposition for the Think stage."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from src.core.agents.engine.loop import AssistantPlanner


@dataclass
class TaskRouter:
    """Route a goal into one or more sub-goals via LLM-based decomposition."""

    planner: AssistantPlanner
    enabled: bool = True

    async def route(self, goal: str) -> List[str]:
        if not self.enabled:
            return [goal]

        prompt = self._build_prompt(goal)
        response = await self.planner([{"role": "user", "content": prompt}], 0)
        return self._parse_response(goal, response)

    def _build_prompt(self, goal: str) -> str:
        return (
            "Assess whether this task is simple or complex. "
            "Return JSON only. "
            'If simple, return: {"type": "simple"}. '
            'If complex, return: {"type": "complex", "sub_goals": ["...", "..."]}. '
            "Sub-goals must be short, sequential, and directly executable.\n\n"
            f"Goal: {goal}"
        )

    def _parse_response(self, goal: str, response: Dict[str, Any]) -> List[str]:
        content = (response.get("content") or "").strip()
        if not content:
            return [goal]

        try:
            data = json.loads(content)
        except Exception:
            return [goal]

        if data.get("type") == "complex":
            sub_goals = data.get("sub_goals") or []
            clean_goals = [str(item).strip() for item in sub_goals if str(item).strip()]
            return clean_goals or [goal]

        return [goal]
