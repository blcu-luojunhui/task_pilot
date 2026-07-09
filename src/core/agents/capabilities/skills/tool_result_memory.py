"""双层工具结果：超长结果首次完整展示，之后用短摘要替代。

实现方式：给 tool 消息打标记 _full（完整内容）与 _summary（短摘要）。
在送入 LLM 前，把"非最近一轮"的超长 tool 消息的 content 替换为 _summary。
"""
from __future__ import annotations

from typing import Any, Dict, List

# 超过该字符数的工具结果才启用双层
TOOL_RESULT_LONG_THRESHOLD = 1500
# 摘要保留的字符数
TOOL_RESULT_SUMMARY_CHARS = 400


def make_summary(content: str) -> str:
    if len(content) <= TOOL_RESULT_SUMMARY_CHARS:
        return content
    head = content[: TOOL_RESULT_SUMMARY_CHARS]
    return (
        f"{head}\n"
        f"[…该工具结果较长，已折叠。完整长度 {len(content)} 字符。"
        f"如需完整内容请重新调用对应工具。]"
    )


def annotate_tool_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """对单条 tool 消息打上 _full / _summary 标记（若超长）。"""
    if msg.get("role") != "tool":
        return msg
    content = msg.get("content") or ""
    if len(content) <= TOOL_RESULT_LONG_THRESHOLD:
        return msg
    msg = dict(msg)
    msg["_full"] = content
    msg["_summary"] = make_summary(content)
    return msg


def collapse_old_tool_results(
    messages: List[Dict[str, Any]],
    keep_full_last_n_tool: int = 2,
) -> List[Dict[str, Any]]:
    """把"较早的"超长 tool 消息替换为摘要；最近 keep_full_last_n_tool 条保留完整。

    返回送入 LLM 用的新列表（不修改入参里的对象语义，content 用摘要）。
    """
    # 找出所有带 _summary 标记的 tool 消息下标
    tool_indices = [
        i for i, m in enumerate(messages)
        if m.get("role") == "tool" and m.get("_summary")
    ]
    keep_full = set(tool_indices[-keep_full_last_n_tool:]) if keep_full_last_n_tool > 0 else set()

    out: List[Dict[str, Any]] = []
    for i, m in enumerate(messages):
        if m.get("role") == "tool" and m.get("_summary") and i not in keep_full:
            collapsed = {k: v for k, v in m.items() if not k.startswith("_")}
            collapsed["content"] = m["_summary"]
            out.append(collapsed)
        else:
            # 去掉内部 _ 前缀字段后送出（LLM 不需要看到 _full/_summary）
            clean = {k: v for k, v in m.items() if not k.startswith("_")}
            out.append(clean)
    return out


__all__ = [
    "annotate_tool_message",
    "collapse_old_tool_results",
    "make_summary",
    "TOOL_RESULT_LONG_THRESHOLD",
]
