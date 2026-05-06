"""
Task Tools - 任务调度和管理工具

封装任务系统能力为 Agent 可调用的技能
"""

import time
from typing import Any, Dict, List, Optional

from src.core.agents.capabilities.skills import skill, SkillContext
from src.jobs.task_utils import TaskUtils


@skill(
    name="task_query_status",
    description="查询任务状态",
    dependencies=["db", "log"],
    risk_level="read",
    parameters={
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
    },
    examples=[
        {"input": {"trace_id": "Agent-20260430-abc123"}, "output": "返回任务完整信息（状态、时间、数据等）"},
    ],
)
async def task_query_status(
    ctx: SkillContext, trace_id: str
) -> Optional[Dict[str, Any]]:
    """查询任务状态"""
    await ctx.log.log({
        "event": "task_query_status",
        "trace_id": trace_id,
    })

    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    row = await ctx.db.async_fetch_one(
        f"SELECT * FROM {table} WHERE trace_id = %s",
        params=(trace_id,),
    )
    return row


@skill(
    name="task_list_processing",
    description="列出指定任务名下所有正在执行的任务",
    dependencies=["db", "log"],
    risk_level="read",
    parameters={
        "task_name": {
            "type": "string",
            "description": "任务名称",
            "required": True,
        },
    },
    examples=[
        {"input": {"task_name": "daily_sync"}, "output": "返回正在执行的任务列表"},
    ],
)
async def task_list_processing(
    ctx: SkillContext, task_name: str
) -> List[Dict[str, Any]]:
    """列出正在执行的任务"""
    await ctx.log.log({
        "event": "task_list_processing",
        "task_name": task_name,
    })

    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    rows = await ctx.db.async_fetch(
        f"SELECT trace_id, start_timestamp, data FROM {table} "
        f"WHERE task_status = 1 AND task_name = %s",
        params=(task_name,),
    )
    return rows or []


@skill(
    name="task_cancel",
    description="请求取消任务（设置取消信号，任务会在下次轮询时取消）",
    dependencies=["db", "log"],
    risk_level="write",
    parameters={
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
    },
    examples=[
        {"input": {"trace_id": "Agent-20260430-abc123"}, "output": "true 表示取消成功，false 表示任务不存在或已完成"},
    ],
)
async def task_cancel(ctx: SkillContext, trace_id: str) -> bool:
    """请求取消任务"""
    await ctx.log.log({
        "event": "task_cancel",
        "trace_id": trace_id,
    })

    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    affected = await ctx.db.async_save(
        f"""
        UPDATE {table}
        SET task_status = CASE
                WHEN task_status = 0 THEN 3
                WHEN task_status = 1 THEN 4
            END,
            finish_timestamp = CASE
                WHEN task_status = 0 THEN UNIX_TIMESTAMP()
                ELSE finish_timestamp
            END
        WHERE trace_id = %s AND task_status IN (0, 1)
        """,
        params=(trace_id,),
    )

    return bool(affected)


@skill(
    name="task_create",
    description="创建新任务记录",
    dependencies=["db", "log"],
    risk_level="write",
    parameters={
        "task_name": {
            "type": "string",
            "description": "任务名称",
            "required": True,
        },
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
        "data": {
            "type": "object",
            "description": "任务附加数据（JSON 格式）",
            "required": False,
        },
    },
    examples=[
        {"input": {"task_name": "daily_sync", "trace_id": "Agent-20260506-xyz"}, "output": "返回创建的任务 trace_id"},
    ],
)
async def task_create(
    ctx: SkillContext,
    task_name: str,
    trace_id: str,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    """创建新任务"""
    import json as json_mod

    await ctx.log.log({
        "event": "task_create",
        "task_name": task_name,
        "trace_id": trace_id,
    })

    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    now = int(time.time())
    date_string = time.strftime("%Y%m%d", time.localtime(now))
    data_json = json_mod.dumps(data or {}, ensure_ascii=False)

    await ctx.db.async_save(
        f"""
        INSERT INTO {table} (date_string, task_name, task_status, start_timestamp, trace_id, data)
        VALUES (%s, %s, 0, %s, %s, %s)
        """,
        params=(date_string, task_name, now, trace_id, data_json),
    )

    return trace_id


# 任务状态机：合法的状态转换
_VALID_TRANSITIONS = {
    0: {1, 3},       # INIT → PROCESSING, CANCELLED
    1: {2, 4, 99},   # PROCESSING → SUCCESS, CANCEL_REQUESTED, FAILED
    4: {3},          # CANCEL_REQUESTED → CANCELLED
}


@skill(
    name="task_update_status",
    description="更新任务状态（带状态机校验，只允许合法的状态转换）",
    dependencies=["db", "log"],
    risk_level="write",
    parameters={
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
        "new_status": {
            "type": "integer",
            "description": "目标状态（0=INIT, 1=PROCESSING, 2=SUCCESS, 3=CANCELLED, 4=CANCEL_REQUESTED, 99=FAILED）",
            "required": True,
            "enum": [0, 1, 2, 3, 4, 99],
        },
    },
    examples=[
        {"input": {"trace_id": "Agent-20260506-xyz", "new_status": 2}, "output": "true 表示更新成功"},
    ],
)
async def task_update_status(
    ctx: SkillContext, trace_id: str, new_status: int
) -> bool:
    """更新任务状态（带状态机校验）"""
    await ctx.log.log({
        "event": "task_update_status",
        "trace_id": trace_id,
        "new_status": new_status,
    })

    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    # 查询当前状态
    row = await ctx.db.async_fetch_one(
        f"SELECT task_status FROM {table} WHERE trace_id = %s",
        params=(trace_id,),
    )
    if not row:
        raise ValueError(f"Task not found: {trace_id}")

    current_status = row["task_status"]
    valid_next = _VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next:
        raise ValueError(
            f"Invalid status transition: {current_status} → {new_status} "
            f"(allowed: {sorted(valid_next)})"
        )

    # 终态时设置 finish_timestamp
    finish_clause = ""
    if new_status in (2, 3, 99):
        finish_clause = ", finish_timestamp = UNIX_TIMESTAMP()"

    affected = await ctx.db.async_save(
        f"UPDATE {table} SET task_status = %s{finish_clause} WHERE trace_id = %s",
        params=(new_status, trace_id),
    )

    return bool(affected)
