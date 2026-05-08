"""
Dynamic prompt assembly for the Think stage.

Builds a per-step system message from current agent state and selected knowledge.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...state import AgentLoopState
from .knowledge_selector import KnowledgeSelector


@dataclass
class PromptAssembler:
    """Build dynamic system prompts for the current agent step."""

    base_instructions: str = "You are an agent that solves the user's goal step by step. Use tools when needed and answer directly when enough information is available."
    max_system_tokens: int = 8000
    knowledge_selector: Optional[KnowledgeSelector] = None

    def assemble(self, state: AgentLoopState) -> Dict[str, Any]:
        sections = [self.base_instructions.strip()]

        sections.append(self._goal_section(state))
        sections.append(self._budget_section(state))

        error_hint = self._error_hint_section(state)
        if error_hint:
            sections.append(error_hint)

        knowledge = self._knowledge_section(state)
        if knowledge:
            sections.append(knowledge)

        content = "\n\n".join(section for section in sections if section)

        # 截断到 max_system_tokens（按 ~4 chars/token 估算）
        max_chars = self.max_system_tokens * 4
        if len(content) > max_chars:
            content = content[:max_chars]

        return {
            "role": "system",
            "content": content,
        }

    def _goal_section(self, state: AgentLoopState) -> str:
        return f"## Goal\n{state.goal}"

    def _budget_section(self, state: AgentLoopState) -> str:
        remaining = max(state.max_steps - state.step, 0)
        return (
            "## Budget\n"
            f"Current step: {state.step}. "
            f"You have {remaining} steps remaining out of {state.max_steps}. "
            "Prefer direct answers when you already have enough information."
        )

    def _error_hint_section(self, state: AgentLoopState) -> str:
        if state.consecutive_tool_errors <= 0:
            return ""
        return (
            "## Recovery Hint\n"
            f"Recent tool errors: {state.consecutive_tool_errors}. "
            "Try a different tool, different parameters, or provide the best possible answer without repeating the same failing action."
        )

    def _knowledge_section(self, state: AgentLoopState) -> str:
        if not self.knowledge_selector:
            return ""
        knowledge = self.knowledge_selector.select(state).strip()
        if not knowledge:
            return ""
        return f"## Reference Knowledge\n{knowledge}"


__all__ = ["PromptAssembler"]
