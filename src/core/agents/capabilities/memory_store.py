"""跨 run 记忆：run 结束生成反思并持久化；下次注入。

依赖注入：db（async MySQL client，需有 async_fetch / async_save）、
provider（LLMProvider）。两者由调用方传入。
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from src.core.agents.capabilities.llm.base import LLMProvider, LLMMessage

logger = logging.getLogger(__name__)

_REFLECT_PROMPT = (
    "你是一个 agent 的复盘助手。下面是一次任务执行的目标与结果摘要。"
    "请用 2-4 条要点总结：哪些做法有效、踩了什么坑、下次同类任务应注意什么。"
    "只输出要点本身，简洁可执行，不要寒暄。"
)

# 单次注入的最多反思条数
_MAX_INJECT = 3


def normalize_scope_key(text: str) -> str:
    """把 goal/task_name 归一化成检索键（取前若干字符的小写）。"""
    return (text or "").strip().lower()[:256]


async def generate_reflection(
    provider: LLMProvider,
    goal: str,
    final_answer: str,
    success: bool,
) -> str:
    summary = (
        f"任务目标：{goal}\n"
        f"是否成功：{'是' if success else '否'}\n"
        f"最终结果：{(final_answer or '')[:2000]}"
    )
    resp = await provider.chat(
        messages=[
            LLMMessage(role="system", content=_REFLECT_PROMPT),
            LLMMessage(role="user", content=summary),
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return (resp.content or "").strip()


async def save_reflection(
    db: Any,
    account_id: int,
    scope_key: str,
    trace_id: str,
    reflection: str,
    success: bool,
) -> None:
    if not reflection:
        return
    await db.async_save(
        "INSERT INTO agent_memory (account_id, scope_key, trace_id, reflection, success) "
        "VALUES (%s, %s, %s, %s, %s)",
        (account_id, scope_key, trace_id, reflection, 1 if success else 0),
    )


async def fetch_reflections(
    db: Any,
    account_id: int,
    scope_key: str,
    limit: int = _MAX_INJECT,
) -> List[str]:
    rows = await db.async_fetch(
        "SELECT reflection FROM agent_memory "
        "WHERE account_id = %s AND scope_key = %s "
        "ORDER BY created_at DESC LIMIT %s",
        params=(account_id, scope_key, limit),
    )
    return [r["reflection"] for r in (rows or []) if r.get("reflection")]


def format_memory_injection(reflections: List[str]) -> Optional[str]:
    if not reflections:
        return None
    body = "\n".join(f"- {r}" for r in reflections)
    return f"## 过往同类任务的经验（供参考，不一定正确）\n{body}"


__all__ = [
    "normalize_scope_key",
    "generate_reflection",
    "save_reflection",
    "fetch_reflections",
    "format_memory_injection",
]
