"""Chat 域工具区域：让 chat agent 能制定计划、启动业务任务、回看历史。

设计原则：
- 只新增 chat 场景独有的能力；查询/取消单个任务直接复用 ``task`` 区域的
  ``task_query_status`` / ``task_cancel``。chat agent 加载
  ``tool_areas=["chat_ops", "task"]`` 即可。
- ``run_task`` 通过 ``task_invoker`` 依赖启动子任务。``task_invoker`` 由
  ``chat.agent_turn`` 在调度时通过 ``tool_dependencies`` 显式注入——避免
  skill 直接拿到完整 deps，权限边界更清晰。
"""
from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional

from src.core.agents.capabilities.skills import skill, SkillContext
from src.jobs.task_utils import TaskUtils


@skill(
    name="plan_tasks",
    description=(
        "在执行实际任务前，把整体计划结构化输出。每个步骤可关联一个 task_name "
        "和参数，用户在 UI 上看到 plan 卡片后会决定是否继续。本身不真正执行任务，"
        "只用于让用户看清你的意图。"
    ),
    risk_level="read",
    parameters={
        "title": {
            "type": "string",
            "description": "计划标题，简短一句概括",
            "required": True,
        },
        "rationale": {
            "type": "string",
            "description": "为什么要这样规划，一两句即可",
            "required": False,
        },
        "steps": {
            "type": "array",
            "description": "步骤列表",
            "required": True,
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "步骤标题",
                    },
                    "description": {
                        "type": "string",
                        "description": "步骤说明（可选）",
                    },
                    "task_name": {
                        "type": "string",
                        "description": "若该步骤需要启动一个 TaskPilot 任务，指定 task_name；否则留空",
                    },
                    "params": {
                        "type": "object",
                        "description": "启动该 task 时传入的参数（可选）",
                    },
                },
                "required": ["title"],
            },
        },
    },
    examples=[
        {
            "input": {
                "title": "执行每日数据同步",
                "rationale": "先确认任务名存在再启动，避免无效调用",
                "steps": [
                    {"title": "确认 task 已注册", "task_name": ""},
                    {"title": "启动 daily_sync", "task_name": "daily_sync"},
                ],
            },
            "output": "返回结构化 plan 给前端渲染",
        }
    ],
)
async def plan_tasks(
    ctx: SkillContext,
    title: str,
    steps: List[Dict[str, Any]],
    rationale: Optional[str] = None,
) -> Dict[str, Any]:
    """结构化输出一个 plan，供前端渲染为 plan 卡片。

    本身不执行任何动作——LLM 后续会基于 user 反馈再决定是否调用 ``run_task``。
    """
    return {
        "type": "plan",
        "title": title,
        "rationale": rationale,
        "steps": [
            {
                "title": s.get("title", ""),
                "description": s.get("description"),
                "task_name": s.get("task_name") or None,
                "params": s.get("params") or None,
            }
            for s in (steps or [])
        ],
    }


@skill(
    name="run_task",
    description=(
        "启动一个 TaskPilot 业务任务。任务在后台异步执行，立即返回 trace_id。"
        "用户可以通过 trace_id 查看进度或取消。注意：先用 task_query_status 验证 "
        "trace_id 存在再继续；不要在同一轮对话里反复启动同名任务。"
    ),
    dependencies=["task_invoker", "log"],
    risk_level="write",
    parameters={
        "task_name": {
            "type": "string",
            "description": "已注册的任务名",
            "required": True,
        },
        "params": {
            "type": "object",
            "description": "传给任务的参数（透传到 task data）",
            "required": False,
        },
        "date_string": {
            "type": "string",
            "description": "任务日期（YYYY-MM-DD），不填则用今天",
            "required": False,
        },
    },
    examples=[
        {
            "input": {"task_name": "daily_sync", "params": {"source": "users"}},
            "output": "{'trace_id': 'Task-...', 'code': 0, 'task_name': 'daily_sync'}",
        }
    ],
)
async def run_task(
    ctx: SkillContext,
    task_name: str,
    params: Optional[Dict[str, Any]] = None,
    date_string: Optional[str] = None,
) -> Dict[str, Any]:
    """启动业务任务，返回 ``{trace_id, code, message, task_name}``。"""
    await ctx.log.log(
        {"event": "chat_run_task", "task_name": task_name, "params": params}
    )
    return await ctx.task_invoker.run(
        task_name=task_name,
        params=params or {},
        date_string=date_string,
    )


@skill(
    name="list_recent_tasks",
    description=(
        "列出最近的任务（任意状态），按开始时间倒序。用于回答用户"
        "类似'最近跑了什么任务'、'有没有失败的任务'这类问题。"
    ),
    dependencies=["db", "log"],
    risk_level="read",
    parameters={
        "limit": {
            "type": "integer",
            "description": "返回条数，默认 10，最多 50",
            "required": False,
        },
        "status": {
            "type": "integer",
            "description": "按状态过滤：0=INIT 1=PROCESSING 2=SUCCESS 3=CANCELLED 4=CANCEL_REQUESTED 99=FAILED；不填则不过滤",
            "required": False,
            "enum": [0, 1, 2, 3, 4, 99],
        },
        "task_name": {
            "type": "string",
            "description": "按任务名过滤（精确匹配）",
            "required": False,
        },
    },
    examples=[
        {"input": {"limit": 5, "status": 99}, "output": "返回最近 5 条失败任务"}
    ],
)
async def list_recent_tasks(
    ctx: SkillContext,
    limit: Optional[int] = 10,
    status: Optional[int] = None,
    task_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 10), 50))
    table = TaskUtils.validate_table_name(
        ctx.config.task_table if ctx.config else "task_manager"
    )

    conditions: List[str] = []
    params: List[Any] = []
    if status is not None:
        conditions.append("task_status = %s")
        params.append(int(status))
    if task_name:
        conditions.append("task_name = %s")
        params.append(task_name)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    await ctx.log.log(
        {"event": "chat_list_recent_tasks", "limit": safe_limit, "status": status, "task_name": task_name}
    )

    rows = await ctx.db.async_fetch(
        f"SELECT trace_id, task_name, task_status, start_timestamp, "
        f"finish_timestamp, data FROM {table} {where} "
        f"ORDER BY start_timestamp DESC LIMIT %s",
        params=(*params, safe_limit),
    )
    items: List[Dict[str, Any]] = []
    for row in rows or []:
        data_raw = row.get("data")
        if isinstance(data_raw, (bytes, bytearray)):
            data_raw = data_raw.decode("utf-8")
        try:
            row["data"] = _json.loads(data_raw) if data_raw else {}
        except (TypeError, ValueError):
            row["data"] = {}
        items.append(row)
    return items


@skill(
    name="escalate_to_agent",
    description=(
        "把当前对话从纯聊天模式升级为 agentic 模式（同一轮内立即解锁 plan_tasks / "
        "run_task 等改状态的工具）。仅当用户的诉求需要制定计划、启动任务、取消任务、"
        "或其他需要写操作时调用。普通问候、闲聊、单纯查询历史不要调用。本身不执行"
        "任何业务动作，只做模式切换；切换后下一轮你会看到完整工具集。"
    ),
    risk_level="read",
    parameters={
        "reason": {
            "type": "string",
            "description": "为什么需要升级，一句话说明用户诉求（中文）",
            "required": True,
        },
    },
    examples=[
        {
            "input": {"reason": "用户要求启动 daily_sync 任务"},
            "output": "{'mode': 'agentic', 'reason': '用户要求启动 daily_sync 任务'}",
        }
    ],
)
async def escalate_to_agent(ctx: SkillContext, reason: str) -> Dict[str, Any]:
    """切换 chat 到 agentic 模式。runner 拦截这个调用做模式切换，结果只是占位。"""
    return {"mode": "agentic", "reason": reason}


__all__ = ["plan_tasks", "run_task", "list_recent_tasks", "escalate_to_agent"]
