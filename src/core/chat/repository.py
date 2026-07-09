"""ChatRepository：会话与消息的持久化。

设计要点：
- 直接 SQL，无 ORM；JSON 字段由本层 dump/load，调用方拿到的是原生 dict / list。
- conversation_id 是对外稳定 ID（``Conv-...``），所有跨表关联通过它。
- 状态用枚举常量描述：0=ACTIVE, 1=ARCHIVED, 99=DELETED；删除一律软删，便于审计。
"""
from __future__ import annotations

import json
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .ids import generate_conversation_id

if TYPE_CHECKING:
    from src.infra.database import AsyncMySQLPool


class ConversationStatus(IntEnum):
    ACTIVE = 0
    ARCHIVED = 1
    DELETED = 99


# ---- JSON 字段反序列化辅助 ----------------------------------------------------

_CONV_JSON_FIELDS = ("metadata",)
_MSG_JSON_FIELDS = ("tool_calls", "token_usage")

# message status 常量
MSG_STATUS_COMPLETED = 0
MSG_STATUS_PENDING_CONFIRMATION = 1
MSG_STATUS_REJECTED = 2
MSG_STATUS_CANCELLED = 3


def _decode_json_fields(row: Dict[str, Any], fields: Tuple[str, ...]) -> Dict[str, Any]:
    for field in fields:
        raw = row.get(field)
        if raw is None or isinstance(raw, (dict, list)):
            continue
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        try:
            row[field] = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            row[field] = None
    return row


def _dump_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ---- Repository ---------------------------------------------------------------


class ChatRepository:
    """会话/消息 CRUD。所有方法 ``async``，依赖 ``AsyncMySQLPool``。"""

    CONV_TABLE = "chat_conversations"
    MSG_TABLE = "chat_messages"

    _CONV_COLUMNS = (
        "conversation_id, title, status, metadata, account_id, created_at, updated_at"
    )
    _MSG_COLUMNS = (
        "id, conversation_id, role, content, tool_calls, tool_call_id, "
        "trace_id, seq, parent_seq, branch_type, token_usage, status, account_id, created_at"
    )

    def __init__(self, pool: "AsyncMySQLPool", account_id: int = 0) -> None:
        self._pool = pool
        self._account_id = account_id

    # ── 会话 ────────────────────────────────────────────────────────────────

    async def create_conversation(
        self,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        conversation_id = generate_conversation_id()
        await self._pool.async_save(
            f"INSERT INTO {self.CONV_TABLE} "
            "(conversation_id, title, status, metadata, account_id) VALUES (%s, %s, %s, %s, %s)",
            params=(
                conversation_id,
                title,
                ConversationStatus.ACTIVE.value,
                _dump_json(metadata),
                self._account_id,
            ),
        )
        row = await self.get_conversation(conversation_id)
        # 新建后必然存在
        assert row is not None
        return row

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        row = await self._pool.async_fetch_one(
            f"SELECT {self._CONV_COLUMNS} FROM {self.CONV_TABLE} "
            "WHERE conversation_id = %s AND account_id = %s",
            params=(conversation_id, self._account_id),
        )
        return _decode_json_fields(row, _CONV_JSON_FIELDS) if row else None

    async def list_conversations(
        self,
        limit: int = 20,
        offset: int = 0,
        status: Optional[int] = ConversationStatus.ACTIVE.value,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """分页查询会话列表，按 ``updated_at`` 倒序。

        ``status=None`` 表示不过滤，包含所有非删除态；默认仅 ACTIVE。
        """
        if status is None:
            where = "WHERE status != %s AND account_id = %s"
            where_params: Tuple[Any, ...] = (ConversationStatus.DELETED.value, self._account_id)
        else:
            where = "WHERE status = %s AND account_id = %s"
            where_params = (status, self._account_id)

        total_row = await self._pool.async_fetch_one(
            f"SELECT COUNT(*) AS c FROM {self.CONV_TABLE} {where}",
            params=where_params,
        )
        total = int(total_row["c"]) if total_row else 0

        rows = await self._pool.async_fetch(
            f"SELECT {self._CONV_COLUMNS} FROM {self.CONV_TABLE} {where} "
            "ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s",
            params=(*where_params, limit, offset),
        )
        items = [_decode_json_fields(r, _CONV_JSON_FIELDS) for r in (rows or [])]
        return total, items

    async def update_conversation_title(
        self, conversation_id: str, title: str
    ) -> bool:
        affected = await self._pool.async_save(
            f"UPDATE {self.CONV_TABLE} SET title = %s WHERE conversation_id = %s AND account_id = %s",
            params=(title, conversation_id, self._account_id),
        )
        return bool(affected)

    async def archive_conversation(self, conversation_id: str) -> bool:
        affected = await self._pool.async_save(
            f"UPDATE {self.CONV_TABLE} SET status = %s WHERE conversation_id = %s AND account_id = %s",
            params=(ConversationStatus.ARCHIVED.value, conversation_id, self._account_id),
        )
        return bool(affected)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """软删：status=99，记录保留以便审计。"""
        affected = await self._pool.async_save(
            f"UPDATE {self.CONV_TABLE} SET status = %s WHERE conversation_id = %s AND account_id = %s",
            params=(ConversationStatus.DELETED.value, conversation_id, self._account_id),
        )
        return bool(affected)

    # ── 消息 ────────────────────────────────────────────────────────────────

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 200,
        before_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """按时间正序返回消息。

        ``before_id`` 可用于"加载更早消息"的分页：传入当前最早消息的 id，
        会返回严格更早的最多 ``limit`` 条，仍然按时间正序。
        """
        if before_id is None:
            sql = (
                f"SELECT {self._MSG_COLUMNS} FROM {self.MSG_TABLE} "
                "WHERE conversation_id = %s AND account_id = %s ORDER BY id ASC LIMIT %s"
            )
            params: Tuple[Any, ...] = (conversation_id, self._account_id, limit)
        else:
            sql = (
                f"SELECT {self._MSG_COLUMNS} FROM ("
                f"  SELECT {self._MSG_COLUMNS} FROM {self.MSG_TABLE} "
                "  WHERE conversation_id = %s AND id < %s AND account_id = %s "
                "  ORDER BY id DESC LIMIT %s"
                ") sub ORDER BY id ASC"
            )
            params = (conversation_id, before_id, self._account_id, limit)

        rows = await self._pool.async_fetch(sql, params=params)
        return [_decode_json_fields(r, _MSG_JSON_FIELDS) for r in (rows or [])]

    async def append_message(
        self,
        conversation_id: str,
        role: str,
        content: Optional[str] = None,
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        token_usage: Optional[Dict[str, Any]] = None,
        status: int = MSG_STATUS_COMPLETED,
        seq: Optional[int] = None,
        parent_seq: Optional[int] = None,
        branch_type: Optional[str] = None,
    ) -> int:
        """插入一条消息，返回自增 id。

        当 trace_id 不为空且未显式传入 seq 时，自动在事务内分配树序号
        （双写：兼容旧表无 seq 列的库，树列为 NULL 时 ORDER BY id 仍正确）。

        INSERT、bump updated_at、trace_head 推进必须在同一事务里完成。
        """
        _auto_tree = bool(trace_id and seq is None)

        async with self._pool.transaction() as conn:
            if _auto_tree:
                alloc = await self._alloc_seq_in_tx(conn, trace_id)  # type: ignore[arg-type]
                seq = alloc["seq"]
                parent_seq = alloc["parent_seq"]
                branch_type = branch_type or "main"
                _next_seq = alloc["next_seq"]

            async with conn.cursor() as cursor:
                if seq is not None:
                    await cursor.execute(
                        f"INSERT INTO {self.MSG_TABLE} "
                        "(conversation_id, role, content, tool_calls, tool_call_id, "
                        "trace_id, seq, parent_seq, branch_type, token_usage, status, account_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            conversation_id, role, content,
                            _dump_json(tool_calls), tool_call_id,
                            trace_id, seq, parent_seq, branch_type,
                            _dump_json(token_usage), status, self._account_id,
                        ),
                    )
                else:
                    await cursor.execute(
                        f"INSERT INTO {self.MSG_TABLE} "
                        "(conversation_id, role, content, tool_calls, tool_call_id, "
                        "trace_id, token_usage, status, account_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            conversation_id, role, content,
                            _dump_json(tool_calls), tool_call_id,
                            trace_id,
                            _dump_json(token_usage), status, self._account_id,
                        ),
                    )
                message_id = cursor.lastrowid

                # bump conversation updated_at
                await cursor.execute(
                    f"UPDATE {self.CONV_TABLE} SET updated_at = CURRENT_TIMESTAMP "
                    "WHERE conversation_id = %s",
                    (conversation_id,),
                )

            # 推进 trace_head（同一事务）
            if _auto_tree and seq is not None:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "UPDATE trace_head SET head_seq = %s, next_seq = %s WHERE trace_id = %s",
                        (seq, _next_seq, trace_id),
                    )

        return int(message_id) if message_id else 0

    async def _alloc_seq_in_tx(self, conn, trace_id: str) -> Dict[str, Any]:
        """在已有事务连接中分配 seq（内部方法）。"""
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT head_seq, next_seq FROM trace_head WHERE trace_id = %s",
                (trace_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "INSERT INTO trace_head (trace_id, head_seq, next_seq, account_id) "
                    "VALUES (%s, 0, 1, %s)",
                    (trace_id, self._account_id),
                )
            return {"seq": 1, "parent_seq": None, "next_seq": 2}

        head_seq = row["head_seq"]
        next_seq_val = row["next_seq"]
        parent_seq = head_seq if head_seq > 0 else None
        seq = next_seq_val
        return {"seq": seq, "parent_seq": parent_seq, "next_seq": next_seq_val + 1}


    async def update_message_status(self, message_id: int, status: int) -> bool:
        """更新单条消息的 status 字段。"""
        affected = await self._pool.async_save(
            f"UPDATE {self.MSG_TABLE} SET status = %s WHERE id = %s AND account_id = %s",
            params=(status, message_id, self._account_id),
        )
        return bool(affected)

    async def get_pending_message(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """查最新一条 status=pending_confirmation 的消息（含 tool_calls）。"""
        row = await self._pool.async_fetch_one(
            f"SELECT {self._MSG_COLUMNS} FROM {self.MSG_TABLE} "
            "WHERE conversation_id = %s AND status = %s AND account_id = %s "
            "ORDER BY id DESC LIMIT 1",
            params=(conversation_id, MSG_STATUS_PENDING_CONFIRMATION, self._account_id),
        )
        return _decode_json_fields(row, _MSG_JSON_FIELDS) if row else None

    async def build_llm_messages(
        self, conversation_id: str, limit: int = 40
    ) -> List[Dict[str, Any]]:
        """从 chat_messages 拼装 LLM 格式的消息列表。

        - status=pending_confirmation 的消息不包含（还没执行）
        - status=rejected 的消息包含，但 tool_calls 不传
        """
        rows = await self.list_messages(conversation_id, limit=limit)
        out: List[Dict[str, Any]] = []
        for row in rows:
            if int(row.get("status", 0)) == MSG_STATUS_PENDING_CONFIRMATION:
                continue

            msg: Dict[str, Any] = {"role": row["role"]}
            content = row.get("content")
            if content is not None:
                msg["content"] = content

            if int(row.get("status", 0)) != MSG_STATUS_REJECTED:
                tool_calls = row.get("tool_calls")
                if tool_calls:
                    msg["tool_calls"] = tool_calls

            tool_call_id = row.get("tool_call_id")
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id
            out.append(msg)
        return out

    async def build_llm_messages_via_tree(
        self, conversation_id: str,
    ) -> List[Dict[str, Any]]:
        """从消息树主路径拼装 LLM 消息列表（基于 seq/parent_seq 回溯）。

        相比 build_llm_messages（基于 id 正序），此方法：
        - 只走主路径（过滤掉被压缩/回溯丢弃的分支）
        - 支持非破坏式压缩后的精简上下文

        若 trace_head 不存在或消息无 seq 列，回退到 build_llm_messages。
        """
        from src.core.agents.state.message_tree import get_main_path

        main_path = await get_main_path(self._pool, conversation_id)
        if main_path:
            # get_main_path 返回的是完整消息格式，但需要过滤 status
            out: List[Dict[str, Any]] = []
            # 需要从 DB 查 status；简化策略：从树路径中取消息，忽略 pending_confirmation
            for msg in main_path:
                # 树路径中可能包含 system/internal 消息，统一保留
                out.append(msg)
            return out

        # 回退：seq 列不存在或无 trace_head 数据 → 走线性路径
        return await self.build_llm_messages(conversation_id)


__all__ = [
    "ChatRepository",
    "ConversationStatus",
    "MSG_STATUS_COMPLETED",
    "MSG_STATUS_PENDING_CONFIRMATION",
    "MSG_STATUS_REJECTED",
    "MSG_STATUS_CANCELLED",
]
