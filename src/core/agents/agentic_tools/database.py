"""
Database Tools - 数据库操作工具

封装 AsyncMySQLPool 为 Agent 可调用的技能
"""

from typing import Any, Dict, List, Optional

from src.core.agents.skills import skill, SkillContext


@skill(
    name="db_query",
    description="从 MySQL 数据库查询数据，返回多行结果",
    dependencies=["db", "log"],
    parameters={
        "query": {
            "type": "string",
            "description": "SQL 查询语句（使用 %s 作为参数占位符）",
            "required": True,
        },
        "params": {
            "type": "array",
            "description": "查询参数列表，对应 SQL 中的 %s 占位符",
            "required": False,
        },
    },
)
async def db_query(
    ctx: SkillContext, query: str, params: Optional[tuple] = None
) -> List[Dict[str, Any]]:
    """查询数据库，返回多行结果"""
    await ctx.log.log({
        "event": "db_query",
        "query": query,
        "params": params,
    })
    rows = await ctx.db.async_fetch(query=query, params=params)
    return rows


@skill(
    name="db_query_one",
    description="从 MySQL 数据库查询单条数据",
    dependencies=["db", "log"],
    parameters={
        "query": {
            "type": "string",
            "description": "SQL 查询语句（使用 %s 作为参数占位符）",
            "required": True,
        },
        "params": {
            "type": "array",
            "description": "查询参数列表",
            "required": False,
        },
    },
)
async def db_query_one(
    ctx: SkillContext, query: str, params: Optional[tuple] = None
) -> Optional[Dict[str, Any]]:
    """查询数据库，返回单条结果"""
    await ctx.log.log({
        "event": "db_query_one",
        "query": query,
        "params": params,
    })
    row = await ctx.db.async_fetch_one(query=query, params=params)
    return row


@skill(
    name="db_execute",
    description="执行 MySQL 数据库写操作（INSERT/UPDATE/DELETE），返回影响行数",
    dependencies=["db", "log"],
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
)
async def db_execute(
    ctx: SkillContext,
    query: str,
    params: Optional[Any] = None,
    batch: bool = False,
) -> int:
    """执行数据库写操作"""
    await ctx.log.log({
        "event": "db_execute",
        "query": query,
        "batch": batch,
        "param_count": len(params) if params else 0,
    })
    affected = await ctx.db.async_save(query=query, params=params, batch=batch)
    return affected
