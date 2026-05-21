"""
从 agent_events 表重建 Agent 运行元数据。

数据来源：run_start / run_end 事件的 payload 字段。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.infra.database import AsyncMySQLPool


async def build_agent_metadata(
    mysql: AsyncMySQLPool,
    trace_id: str,
) -> Optional[Dict[str, Any]]:
    """从 agent_events 表重建 agent_metadata"""
    events = await mysql.async_fetch(
        "SELECT event_type, payload FROM agent_events "
        "WHERE trace_id = %s AND event_type IN ('run_start', 'run_end') "
        "ORDER BY sequence",
        params=(trace_id,),
    )
    if not events:
        return None

    run_start: Optional[Dict] = None
    run_end: Optional[Dict] = None
    for e in events:
        payload = e.get("payload")
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        if e["event_type"] == "run_start":
            run_start = payload or {}
        elif e["event_type"] == "run_end":
            run_end = payload or {}

    meta: Dict[str, Any] = {}

    if run_start:
        start_meta = run_start.get("metadata", {})
        if isinstance(start_meta, str):
            import json
            start_meta = json.loads(start_meta)
        meta.update(start_meta)
        if run_start.get("goal"):
            meta["goal"] = run_start["goal"]

    # 兜底：历史 trace（run_start 没 goal 时从 agent_run_summaries 查）
    if not meta.get("goal"):
        row = await mysql.async_fetch_one(
            "SELECT goal FROM agent_run_summaries WHERE trace_id = %s",
            params=(trace_id,),
        )
        if row and row.get("goal"):
            meta["goal"] = row["goal"]

    if run_end:
        result = run_end.get("result", {})
        meta["stop_reason"] = result.get("stop_reason", "")
        meta["total_steps"] = result.get("total_steps", 0)
        meta["tool_calls_count"] = result.get("tool_calls_count", 0)
        meta["final_answer"] = result.get("final_answer")
        meta["token_usage"] = result.get("token_usage", {})
        meta["duration_seconds"] = result.get("duration_seconds", 0)

    return meta


def normalize_event(db_row: Dict[str, Any]) -> Dict[str, Any]:
    """将 DB 行映射为前端 TraceEvent schema（与 SSE 格式一致）"""
    payload = db_row.get("payload")
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    return {
        "sequence": db_row["sequence"],
        "type": db_row["event_type"],
        "source": db_row["source"],
        "step": db_row.get("step"),
        "timestamp": db_row["created_at"].isoformat() if hasattr(db_row["created_at"], "isoformat") else str(db_row["created_at"]),
        "data": payload or {},
    }
