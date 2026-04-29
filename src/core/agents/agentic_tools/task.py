"""
Task Tools - 任务调度和管理工具

封装任务系统能力为 Agent 可调用的技能
"""

from typing import Any, Dict, Optional

from src.core.agents.skills import skill, SkillContext
from src.jobs.task_utils import TaskUtils


@skill(
    name="task_query_status",
    description="查询任务状态",
    dependencies=["db", "log"],
    parameters={
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
    },
)
async def task_query_status(
    ctx: SkillContext, trace_id: str
) -> Optional[Dict[str, Any]]:
    """查询任务状态"""
    await ctx.log.log({
        "event": "task_query_status",
        "trace_id": trace_id,
    })

    # 从配置获取表名并验证
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
    parameters={
        "task_name": {
            "type": "string",
            "description": "任务名称",
            "required": True,
        },
    },
)
async def task_list_processing(
    ctx: SkillContext, task_name: str
) -> list:
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
    parameters={
        "trace_id": {
            "type": "string",
            "description": "任务追踪 ID",
            "required": True,
        },
    },
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

    # 将 INIT 或 PROCESSING 状态的任务标记为 CANCEL_REQUESTED
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
