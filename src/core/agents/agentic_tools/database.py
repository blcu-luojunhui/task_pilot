"""
Database Tools - 数据库操作工具

封装 AsyncMySQLPool 为 Agent 可调用的技能
"""

from typing import Any, Dict, List, Optional

from src.core.agents.skills import skill, SkillContext
from src.core.agents.skills.sql_filter import QUERY_FILTER, EXECUTE_FILTER


@skill(
    name="db_query",
    description="从 MySQL 数据库查询数据，返回多行结果。仅支持 SELECT 语句。",
    dependencies=["db", "log"],
    risk_level="read",
    parameters={
        "query": {
            "type": "string",
            "description": "SQL SELECT 查询语句（使用 %s 作为参数占位符）",
            "required": True,
        },
        "params": {
            "type": "array",
            "description": "查询参数列表，对应 SQL 中的 %s 占位符",
            "required": False,
        },
    },
    examples=[
        {
            "input": {"query": "SELECT * FROM task_manager WHERE trace_id = %s", "params": ["Agent-20260430-abc"]},
            "output": "返回匹配的任务记录列表",
        },
    ],
)
async def db_query(
    ctx: SkillContext, query: str, params: Optional[tuple] = None
) -> List[Dict[str, Any]]:
    """查询数据库，返回多行结果"""
    error = QUERY_FILTER.validate(query, "db_query")
    if error:
        raise ValueError(error)

    await ctx.log.log({
        "event": "db_query",
        "query": query,
        "params": params,
    })
    rows = await ctx.db.async_fetch(query=query, params=params)
    return rows


@skill(
    name="db_query_one",
    description="从 MySQL 数据库查询单条数据。仅支持 SELECT 语句。",
    dependencies=["db", "log"],
    risk_level="read",
    parameters={
        "query": {
            "type": "string",
            "description": "SQL SELECT 查询语句（使用 %s 作为参数占位符）",
            "required": True,
        },
        "params": {
            "type": "array",
            "description": "查询参数列表",
            "required": False,
        },
    },
    examples=[
        {
            "input": {"query": "SELECT task_status FROM task_manager WHERE trace_id = %s", "params": ["Agent-20260430-abc"]},
            "output": "返回单条任务记录或 null",
        },
    ],
)
async def db_query_one(
    ctx: SkillContext, query: str, params: Optional[tuple] = None
) -> Optional[Dict[str, Any]]:
    """查询数据库，返回单条结果"""
    error = QUERY_FILTER.validate(query, "db_query_one")
    if error:
        raise ValueError(error)

    await ctx.log.log({
        "event": "db_query_one",
        "query": query,
        "params": params,
    })
    row = await ctx.db.async_fetch_one(query=query, params=params)
    return row


@skill(
    name="db_execute",
    description="执行 MySQL 数据库写操作（INSERT/UPDATE/DELETE），返回影响行数。禁止 DROP/TRUNCATE/ALTER 等危险操作。",
    dependencies=["db", "log"],
    risk_level="write",
    parameters={
        "query": {
            "type": "string",
            "description": "SQL 语句（使用 %s 作为参数占位符）",
            "required": True,
        },
        "params": {
            "type": "array",
            "description": "参数列表或参数列表的列表（批量操作）",
            "required": False,
        },
        "batch": {
            "type": "boolean",
            "description": "是否批量执行（params 为列表的列表）",
            "default": False,
        },
    },
    examples=[
        {
            "input": {"query": "UPDATE task_manager SET task_status = %s WHERE trace_id = %s", "params": [2, "Agent-20260430-abc"]},
            "output": "返回影响行数，如 1",
        },
    ],
)
async def db_execute(
    ctx: SkillContext,
    query: str,
    params: Optional[Any] = None,
    batch: bool = False,
) -> int:
    """执行数据库写操作"""
    error = EXECUTE_FILTER.validate(query, "db_execute")
    if error:
        raise ValueError(error)

    await ctx.log.log({
        "event": "db_execute",
        "query": query,
        "batch": batch,
        "param_count": len(params) if params else 0,
    })
    affected = await ctx.db.async_save(query=query, params=params, batch=batch)
    return affected
