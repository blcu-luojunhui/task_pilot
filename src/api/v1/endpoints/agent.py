"""Agent Run API：POST /api/agent/run — 目标驱动 agent 执行。

前端拿到 trace_id 后通过 SSE ``/api/task_events/<trace_id>`` 消费实时事件。
"""
from __future__ import annotations

from typing import Any, Dict

from quart import Blueprint, jsonify, request

from src.api.middleware.trace import get_current_trace_id
from src.api.v1.utils import ApiDependencies
from src.infra.shared import ErrorCode
from src.jobs import TaskScheduler

# 触发 agent.run_goal 的 @register 装饰器（与 chat.agent_turn 相同模式）
from src.core.agent_task import run_agent_goal as _run_agent_goal  # noqa: F401

_AGENT_TASK_NAME = "agent.run_goal"
_AVAILABLE_TOOL_AREAS = ["database", "http", "task", "utils", "chat_ops"]


def _bad_request(message: str) -> tuple:
    return jsonify({"code": ErrorCode.VALIDATION_ERROR, "message": message}), 400


def create_agent_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("agent", __name__)

    @bp.route("/agent/tool_areas", methods=["GET"])
    async def list_tool_areas():
        """返回可用的工具区域列表，供前端技能选择器使用。"""
        return jsonify(
            {
                "code": 0,
                "data": {
                    "tool_areas": _AVAILABLE_TOOL_AREAS,
                },
            }
        )

    @bp.route("/agent/run", methods=["POST"])
    async def run_agent():
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        goal = (body.get("goal") or "").strip()
        tool_areas = body.get("tool_areas") or []

        if not goal:
            return _bad_request("goal is required and must be a non-empty string")
        if not isinstance(tool_areas, list) or not all(isinstance(a, str) for a in tool_areas):
            return _bad_request("tool_areas must be a list of strings")

        # 过滤只允许已知工具区域
        safe_areas = [a for a in tool_areas if a in _AVAILABLE_TOOL_AREAS]
        if not safe_areas:
            safe_areas = ["chat_ops", "task"]

        trace_id = get_current_trace_id()

        # 预创建 trace，避免前端 SSE 抢跑命中 404
        try:
            deps.events.ensure_trace(
                trace_id,
                metadata={"task_name": _AGENT_TASK_NAME, "goal": goal[:200]},
            )
        except Exception:
            pass

        scheduler_data = {
            "task_name": _AGENT_TASK_NAME,
            "goal": goal,
            "tool_areas": safe_areas,
        }
        scheduler = TaskScheduler(scheduler_data, trace_id, deps)
        result = await scheduler.deal()

        if isinstance(result, dict) and result.get("code") == 0:
            inner = result.get("data") or {}
            return jsonify(
                {
                    "code": 0,
                    "message": inner.get("message") or "agent run started",
                    "trace_id": inner.get("trace_id") or trace_id,
                    "data": {
                        "trace_id": inner.get("trace_id") or trace_id,
                        "tool_areas": safe_areas,
                    },
                }
            )
        return jsonify(result)

    return bp


__all__ = ["create_agent_bp"]
