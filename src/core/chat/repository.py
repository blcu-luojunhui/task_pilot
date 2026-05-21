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
        "conversation_id, title, status, metadata, created_at, updated_at"
    )
    _MSG_COLUMNS = (
        "id, conversation_id, role, content, tool_calls, tool_call_id, "
        "trace_id, token_usage, status, created_at"
    )

    def __init__(self, pool: "AsyncMySQLPool") -> None:
        self._pool = pool

    # ── 会话 ────────────────────────────────────────────────────────────────

    async def create_conversation(
        self,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        conversation_id = generate_conversation_id()
        await self._pool.async_save(
            f"INSERT INTO {self.CONV_TABLE} "
            "(conversation_id, title, status, metadata) VALUES (%s, %s, %s, %s)",
            params=(
                conversation_id,
                title,
                ConversationStatus.ACTIVE.value,
                _dump_json(metadata),
            ),
        )
        row = await self.get_conversation(conversation_id)
        # 新建后必然存在
        assert row is not None
        return row

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        row = await self._pool.async_fetch_one(
            f"SELECT {self._CONV_COLUMNS} FROM {self.CONV_TABLE} "
            "WHERE conversation_id = %s",
            params=(conversation_id,),
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
            where = "WHERE status != %s"
            where_params: Tuple[Any, ...] = (ConversationStatus.DELETED.value,)
        else:
            where = "WHERE status = %s"
            where_params = (status,)

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
            f"UPDATE {self.CONV_TABLE} SET title = %s WHERE conversation_id = %s",
            params=(title, conversation_id),
        )
        return bool(affected)

    async def archive_conversation(self, conversation_id: str) -> bool:
        affected = await self._pool.async_save(
            f"UPDATE {self.CONV_TABLE} SET status = %s WHERE conversation_id = %s",
            params=(ConversationStatus.ARCHIVED.value, conversation_id),
        )
        return bool(affected)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """软删：status=99，记录保留以便审计。"""
        affected = await self._pool.async_save(
            f"UPDATE {self.CONV_TABLE} SET status = %s WHERE conversation_id = %s",
            params=(ConversationStatus.DELETED.value, conversation_id),
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
                "WHERE conversation_id = %s ORDER BY id ASC LIMIT %s"
            )
            params: Tuple[Any, ...] = (conversation_id, limit)
        else:
            sql = (
                f"SELECT {self._MSG_COLUMNS} FROM ("
                f"  SELECT {self._MSG_COLUMNS} FROM {self.MSG_TABLE} "
                "  WHERE conversation_id = %s AND id < %s "
                "  ORDER BY id DESC LIMIT %s"
                ") sub ORDER BY id ASC"
            )
            params = (conversation_id, before_id, limit)

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
    ) -> int:
        """插入一条消息，返回自增 id。

        INSERT、bump updated_at、取 lastrowid 必须在同一连接同一事务里完成——
        ``LAST_INSERT_ID()`` 是 session 级别的，跨连接拿不到。
        """
        async with self._pool.transaction() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"INSERT INTO {self.MSG_TABLE} "
                    "(conversation_id, role, content, tool_calls, tool_call_id, "
                    "trace_id, token_usage, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        conversation_id,
                        role,
                        content,
                        _dump_json(tool_calls),
                        tool_call_id,
                        trace_id,
                        _dump_json(token_usage),
                        status,
                    ),
                )
                message_id = cursor.lastrowid
                await cursor.execute(
                    f"UPDATE {self.CONV_TABLE} SET updated_at = CURRENT_TIMESTAMP "
                    "WHERE conversation_id = %s",
                    (conversation_id,),
                )
        return int(message_id) if message_id else 0


    async def update_message_status(self, message_id: int, status: int) -> bool:
        """更新单条消息的 status 字段。"""
        affected = await self._pool.async_save(
            f"UPDATE {self.MSG_TABLE} SET status = %s WHERE id = %s",
            params=(status, message_id),
        )
        return bool(affected)

    async def get_pending_message(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """查最新一条 status=pending_confirmation 的消息（含 tool_calls）。"""
        row = await self._pool.async_fetch_one(
            f"SELECT {self._MSG_COLUMNS} FROM {self.MSG_TABLE} "
            "WHERE conversation_id = %s AND status = %s "
            "ORDER BY id DESC LIMIT 1",
            params=(conversation_id, MSG_STATUS_PENDING_CONFIRMATION),
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


__all__ = [
    "ChatRepository",
    "ConversationStatus",
    "MSG_STATUS_COMPLETED",
    "MSG_STATUS_PENDING_CONFIRMATION",
    "MSG_STATUS_REJECTED",
    "MSG_STATUS_CANCELLED",
]
