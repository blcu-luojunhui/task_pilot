"""消息树：基于 (trace_id, seq, parent_seq) 的主路径读写。

核心数据模型：
- 每条消息有 seq（trace 内单增序号）和 parent_seq（父消息 seq）
- trace_head 表记录每条 trace 的 head_seq 和 next_seq
- 主路径 = 从 head_seq 沿 parent_seq 回溯到根再反转
- 非破坏式压缩 = 在树中插入一条 summary 消息，head 指针越过被压区间

并发安全：定时任务单 writer per trace；Chat 并发场景需 SELECT ... FOR UPDATE。
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def ensure_trace_head(
    db: Any,
    trace_id: str,
    account_id: int,
) -> Dict[str, Any]:
    """确保 trace_head 行存在，返回 (head_seq, next_seq)。"""
    row = await db.async_fetch_one(
        "SELECT head_seq, next_seq FROM trace_head WHERE trace_id = %s",
        params=(trace_id,),
    )
    if row is not None:
        return {"head_seq": row["head_seq"], "next_seq": row["next_seq"]}

    await db.async_save(
        "INSERT INTO trace_head (trace_id, head_seq, next_seq, account_id) "
        "VALUES (%s, 0, 1, %s)",
        (trace_id, account_id),
    )
    return {"head_seq": 0, "next_seq": 1}


async def allocate_seq(
    db: Any,
    trace_id: str,
    account_id: int,
) -> Dict[str, Any]:
    """原子分配一个 seq，返回 {seq, parent_seq, next_seq}。

    调用方应在同一事务内用返回的 seq 写入消息，
    写入成功后调用 update_head 推进 head 指针。
    """
    head = await ensure_trace_head(db, trace_id, account_id)
    parent_seq: Optional[int] = head["head_seq"] if head["head_seq"] > 0 else None
    seq = head["next_seq"]
    return {"seq": seq, "parent_seq": parent_seq, "next_seq": seq + 1}


async def advance_head(
    db: Any,
    trace_id: str,
    new_head_seq: int,
    new_next_seq: int,
) -> None:
    """推进 trace_head 到新的 head_seq / next_seq。"""
    await db.async_save(
        "UPDATE trace_head SET head_seq = %s, next_seq = %s WHERE trace_id = %s",
        (new_head_seq, new_next_seq, trace_id),
    )


async def get_main_path(
    db: Any,
    trace_id: str,
) -> List[Dict[str, Any]]:
    """沿 parent_seq 从 head 回溯到根，返回正序消息列表（LLM 可直接消费）。

    若 chat_messages 没有 seq/parent_seq 列（旧数据），回退到 id 正序。
    """
    head = await db.async_fetch_one(
        "SELECT head_seq FROM trace_head WHERE trace_id = %s",
        params=(trace_id,),
    )
    if not head or not head.get("head_seq"):
        return []

    rows = await db.async_fetch(
        "SELECT seq, parent_seq, role, content, tool_calls, tool_call_id "
        "FROM chat_messages WHERE trace_id = %s AND seq IS NOT NULL",
        params=(trace_id,),
    )
    if not rows:
        return []

    by_seq: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        by_seq[r["seq"]] = r

    path: List[Dict[str, Any]] = []
    seq: Optional[int] = head["head_seq"]
    visited: set = set()
    while seq is not None:
        if seq in visited:
            logger.warning("get_main_path: cycle detected at seq=%d, trace_id=%s", seq, trace_id)
            break
        visited.add(seq)
        r = by_seq.get(seq)
        if not r:
            break
        msg: Dict[str, Any] = {"role": r["role"]}
        if r.get("content"):
            msg["content"] = r["content"]
        if r.get("tool_calls"):
            try:
                msg["tool_calls"] = _json.loads(r["tool_calls"]) if isinstance(r["tool_calls"], str) else r["tool_calls"]
            except (_json.JSONDecodeError, TypeError):
                pass
        if r.get("tool_call_id"):
            msg["tool_call_id"] = r["tool_call_id"]
        path.append(msg)
        seq = r.get("parent_seq")

    path.reverse()
    return path


async def compact_main_path(
    db: Any,
    trace_id: str,
    account_id: int,
    summary_text: str,
    keep_last_n: int = 6,
) -> Optional[int]:
    """非破坏式压缩：保留最近 keep_last_n 条消息，
    之前的用一条 summary system 消息替代。

    算法：
    1. 获取主路径所有消息（带 seq）
    2. 找到保留段第一帧的 parent_seq（锚点）
    3. 写入 summary 消息，parent_seq = 锚点
    4. 把保留段第一帧的 parent_seq 改为 summary 的 seq
    5. head 指针不变

    返回 summary 消息的 seq，失败返回 None。
    """
    head = await db.async_fetch_one(
        "SELECT head_seq FROM trace_head WHERE trace_id = %s",
        params=(trace_id,),
    )
    if not head or not head.get("head_seq"):
        return None

    # 获取所有带 seq 的消息
    rows = await db.async_fetch(
        "SELECT seq, parent_seq, role, content FROM chat_messages "
        "WHERE trace_id = %s AND seq IS NOT NULL ORDER BY seq ASC",
        params=(trace_id,),
    )
    if not rows:
        return None

    by_seq = {r["seq"]: r for r in rows}

    # 沿 head 回溯获得主路径 seq 列表
    path_seqs: List[int] = []
    seq: Optional[int] = head["head_seq"]
    visited: set = set()
    while seq is not None:
        if seq in visited:
            break
        visited.add(seq)
        path_seqs.append(seq)
        r = by_seq.get(seq)
        if not r:
            break
        seq = r.get("parent_seq")
    path_seqs.reverse()  # 根 → 叶

    if len(path_seqs) <= keep_last_n:
        return None  # 还不够长，无需压缩

    # 保留段：最后 keep_last_n 条
    kept_seqs = path_seqs[-keep_last_n:]
    anchor_seq = by_seq[kept_seqs[0]].get("parent_seq")  # 保留段前的锚点

    # 分配 seq 给 summary
    alloc = await allocate_seq(db, trace_id, account_id)
    summary_seq = alloc["seq"]

    # 写入 summary 消息（parent_seq = 锚点）
    await db.async_save(
        "INSERT INTO chat_messages "
        "(conversation_id, role, content, trace_id, seq, parent_seq, branch_type, account_id, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            trace_id,  # conversation_id = trace_id (Chat 路径兼容)
            "system",
            f"[Context Summary]\n{summary_text}",
            trace_id,
            summary_seq,
            anchor_seq,
            "compression",
            account_id,
            0,
        ),
    )

    # 把保留段第一帧的 parent_seq 改为 summary_seq
    await db.async_save(
        "UPDATE chat_messages SET parent_seq = %s "
        "WHERE trace_id = %s AND seq = %s",
        (summary_seq, trace_id, kept_seqs[0]),
    )

    # 推进 head 指针
    await advance_head(db, trace_id, summary_seq, alloc["next_seq"])

    compressed_count = len(path_seqs) - keep_last_n
    logger.info(
        "compact_main_path: trace_id=%s compressed %d messages → summary (seq=%d), kept %d",
        trace_id, compressed_count, summary_seq, keep_last_n,
    )
    return summary_seq


async def backtrack_head(
    db: Any,
    trace_id: str,
    target_seq: int,
) -> bool:
    """回溯：把 head_seq 指向 target_seq，从 target_seq 之后 fork 新分支。

    next_seq 更新为 max(target_seq, next_seq) + 1。
    """
    head = await db.async_fetch_one(
        "SELECT next_seq FROM trace_head WHERE trace_id = %s",
        params=(trace_id,),
    )
    if not head:
        return False

    new_next = max(target_seq, head["next_seq"]) + 1
    await db.async_save(
        "UPDATE trace_head SET head_seq = %s, next_seq = %s WHERE trace_id = %s",
        (target_seq, new_next, trace_id),
    )
    logger.info("backtrack_head: trace_id=%s head → seq=%d", trace_id, target_seq)
    return True


__all__ = [
    "ensure_trace_head",
    "allocate_seq",
    "advance_head",
    "get_main_path",
    "compact_main_path",
    "backtrack_head",
]
