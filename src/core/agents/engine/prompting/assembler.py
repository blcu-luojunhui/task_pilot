"""
Dynamic prompt assembly for the Think stage.

Builds a per-step system message from current agent state and selected knowledge.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ...state import AgentLoopState
from ...state.context.tokenizer import TokenCounter
from .knowledge_selector import KnowledgeSelector

if TYPE_CHECKING:
    from src.core.yggdrasil import ContextAssembler, TreeRetriever

logger = logging.getLogger("agent.prompting")

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
    yggdrasil_retriever: "Optional[TreeRetriever]" = None
    yggdrasil_assembler: "Optional[ContextAssembler]" = None

    def __post_init__(self):
        if self.token_counter is None:
            self.token_counter = TokenCounter()

    async def assemble(self, state: AgentLoopState) -> Dict[str, Any]:
        if self.chat_mode:
            return self._assemble_chat(state)
        return await self._assemble_agent(state)

    async def _assemble_agent(self, state: AgentLoopState) -> Dict[str, Any]:
        sections = [
            ("base", self.base_instructions.strip()),
            ("goal", self._goal_section(state)),
        ]

        plan_section = self._plan_section(state)
        if plan_section:
            sections.append(("plan", plan_section))

        sections.append(("budget", self._budget_section(state)))

        error_hint = self._error_hint_section(state)
        if error_hint:
            sections.append(("error_hint", error_hint))

        knowledge = await self._knowledge_section(state)
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

    def _plan_section(self, state: AgentLoopState) -> str:
        plan = getattr(state, "plan", []) or []
        if not plan:
            return ""
        status_icon = {
            "pending": "⬜",
            "in_progress": "🔄",
            "done": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }
        lines = ["## Plan"]
        for s in plan:
            icon = status_icon.get(s.status.value if hasattr(s, "status") else s.get("status", "pending"), "⬜")
            goal = s.goal if hasattr(s, "goal") else s.get("goal", "")
            lines.append(f"  {icon} [{s.status}] {goal}")
        return "\n".join(lines)

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

    async def _knowledge_section(self, state: AgentLoopState) -> str:
        # 优先使用 Yggdrasil 子树检索
        if self.yggdrasil_retriever and self.yggdrasil_assembler:
            return await self._yggdrasil_section(state)

        if not self.knowledge_selector:
            return ""
        knowledge = self.knowledge_selector.select(state).strip()
        if not knowledge:
            return ""
        return f"## Reference Knowledge\n{knowledge}"

    async def _yggdrasil_section(self, state: AgentLoopState) -> str:
        """使用 Yggdrasil 子树检索获取拓扑相关的上下文"""
        try:
            subtree = await self.yggdrasil_retriever.retrieve_subtree(
                intent=state.goal,
                max_tokens=self.max_system_tokens // 3,
            )
            return self.yggdrasil_assembler.assemble_prompt_injection(subtree)
        except Exception as e:
            logger.warning("Yggdrasil retrieval failed, falling back to legacy: %s", e)
            if self.knowledge_selector:
                knowledge = self.knowledge_selector.select(state).strip()
                if knowledge:
                    return f"## Reference Knowledge\n{knowledge}"
            return ""


__all__ = ["PromptAssembler"]
