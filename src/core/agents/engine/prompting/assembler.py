"""
Dynamic prompt assembly for the Think stage.

Builds a per-step system message from current agent state and selected knowledge.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ...state import AgentLoopState
from ...state.context.tokenizer import TokenCounter
from .knowledge_selector import KnowledgeSelector


_CHAT_INSTRUCTIONS = (
    "You are a helpful assistant. Reply concisely and naturally in a conversational tone. "
    "Use tools only when the user explicitly asks you to perform an action — "
    "most questions should be answered directly."
)


@dataclass
class PromptAssembler:
    """Build dynamic system prompts for the current agent step."""

    base_instructions: str = "You are an agent that solves the user's goal step by step. Use tools when needed and answer directly when enough information is available."
    max_system_tokens: int = 8000
    knowledge_selector: Optional[KnowledgeSelector] = None
    token_counter: Optional[TokenCounter] = None
    chat_mode: bool = False

    def __post_init__(self):
        if self.token_counter is None:
            self.token_counter = TokenCounter()

    def assemble(self, state: AgentLoopState) -> Dict[str, Any]:
        if self.chat_mode:
            return self._assemble_chat(state)
        return self._assemble_agent(state)

    def _assemble_agent(self, state: AgentLoopState) -> Dict[str, Any]:
        sections = [
            ("base", self.base_instructions.strip()),
            ("goal", self._goal_section(state)),
            ("budget", self._budget_section(state)),
        ]

        error_hint = self._error_hint_section(state)
        if error_hint:
            sections.append(("error_hint", error_hint))

        knowledge = self._knowledge_section(state)
        if knowledge:
            sections.append(("knowledge", knowledge))

        # 按优先级组装：低优先级的 section 先被丢弃
        # 优先级: base > goal > budget > error_hint > knowledge
        content_parts: List[str] = []
        used_tokens = 0
        assert self.token_counter is not None

        for _name, text in sections:
            part_tokens = self.token_counter.count(text) + 2  # 分隔符开销
            if used_tokens + part_tokens > self.max_system_tokens:
                break
            content_parts.append(text)
            used_tokens += part_tokens

        content = "\n\n".join(content_parts)

        return {
            "role": "system",
            "content": content,
        }

    def _assemble_chat(self, state: AgentLoopState) -> Dict[str, Any]:
        """Chat 模式：轻量 system prompt，无 budget/goal/step 计数。"""
        return {
            "role": "system",
            "content": _CHAT_INSTRUCTIONS,
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
