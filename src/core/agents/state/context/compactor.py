"""LLM 驱动的上下文压缩器（compactor）。

ContextWindowManager.compactor 期望一个 async callable:
    async def compactor(messages: list[dict]) -> str
返回对这批历史消息的摘要文本。

本模块用现有 LLMProvider 构造这样一个 callable。失败时抛异常，
由 ContextWindowManager 自行回退到截断（已实现）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from src.core.agents.capabilities.llm.base import LLMProvider, LLMMessage

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话历史压缩器。下面是一个 AI agent 执行任务过程中的历史消息"
    "（包含它的思考、工具调用与工具返回结果）。请把它们压缩成一段简洁但信息完整的摘要，"
    "必须保留：1) 已确认的关键事实与数据；2) 已完成的步骤及其结论；3) 尚未解决的问题与待办；"
    "4) 重要的工具返回结果中的关键值（如 ID、数字、状态）。"
    "不要编造信息，不要输出与历史无关的内容。直接输出摘要正文，不要加前言。"
)


def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls")
        if tool_calls:
            names = []
            for tc in tool_calls:
                fn = tc.get("function", tc)
                names.append(fn.get("name", "?"))
            lines.append(f"[{role}] (调用工具: {', '.join(names)}) {content}")
        else:
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def build_llm_compactor(
    provider: LLMProvider,
    max_summary_tokens: int = 1024,
) -> Callable[[List[Dict[str, Any]]], Any]:
    """返回一个 async compactor(messages)->str。"""

    async def _compact(messages: List[Dict[str, Any]]) -> str:
        text = _messages_to_text(messages)
        llm_messages = [
            LLMMessage(role="system", content=_SUMMARY_SYSTEM_PROMPT),
            LLMMessage(role="user", content=text),
        ]
        resp = await provider.chat(
            messages=llm_messages,
            tools=None,
            temperature=0.3,
            max_tokens=max_summary_tokens,
        )
        summary = (resp.content or "").strip()
        if not summary:
            raise ValueError("compactor: empty summary from LLM")
        logger.info("compactor: summarized %d messages -> %d chars", len(messages), len(summary))
        return summary

    return _compact


__all__ = ["build_llm_compactor"]
