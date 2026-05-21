from __future__ import annotations

import asyncio
import json
from typing import List, Tuple

from pydantic import ValidationError
from quart import Blueprint, Response, jsonify, current_app, request

from src.jobs import TaskScheduler
from src.api.v1.utils import ApiDependencies
from src.api.v1.utils import RunTaskRequest, CancelTaskRequest
from src.api.v1.utils import parse_json, validation_error_response
from src.api.v1.utils import decode_json_columns, decode_json_row
from src.api.middleware.trace import get_current_trace_id
from src.infra.shared import ErrorCode


def _escape_like(value: str) -> str:
    """转义 LIKE 模式中的通配符 % 和 _"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_tasks_filter(
    status_filter: List[str],
    task_name: str,
    date: str,
    trace_id_q: str,
) -> Tuple[str, List]:
    """构建任务列表过滤 SQL 子句与参数列表（参数化查询，防 SQL 注入）"""
    conditions: List[str] = []
    params: List = []

    if status_filter:
        placeholders = ",".join(["%s"] * len(status_filter))
        conditions.append(f"task_status IN ({placeholders})")
        params.extend(int(s) for s in status_filter)

    if task_name:
        conditions.append("task_name LIKE %s")
        params.append(f"%{_escape_like(task_name)}%")

    if date:
        conditions.append("date_string = %s")
        params.append(date)

    if trace_id_q:
        conditions.append("trace_id LIKE %s")
        params.append(f"%{_escape_like(trace_id_q)}%")

    sql = ""
    if conditions:
        sql = "WHERE " + " AND ".join(conditions)
    return sql, params


def create_tasks_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("tasks", __name__)

    @bp.route("/run_task", methods=["POST"])
    async def run_task():
        if not current_app.config.get("ACCEPTING_TASKS", True):
            return jsonify(
                {"code": ErrorCode.SERVICE_SHUTTING_DOWN, "message": "Server is shutting down"}
            ), 503

        trace_id = get_current_trace_id()

        try:
            _, body = await parse_json(RunTaskRequest)
        except ValidationError as e:
            payload, status = validation_error_response(e)
            return jsonify(payload), status

        scheduler = TaskScheduler(body, trace_id, deps)
        result = await scheduler.deal()

        # 适配前端 RunTaskResponse：把 trace_id 提到顶层
        if isinstance(result, dict) and result.get("code") == 0:
            inner = result.get("data") or {}
            flat = {
                "code": 0,
                "message": inner.get("message") or result.get("message", "Task started successfully"),
                "trace_id": inner.get("trace_id") or trace_id,
                "data": inner,
            }
            return jsonify(flat)
        return jsonify(result)

    @bp.route("/cancel_task", methods=["POST"])
    async def cancel_task():
        try:
            _, body = await parse_json(CancelTaskRequest)
        except ValidationError as e:
            payload, status = validation_error_response(e)
            return jsonify(payload), status

        trace_id = body["trace_id"]
        scheduler = TaskScheduler(body, trace_id, deps)
        success = await scheduler.cancel_task(trace_id)

        return jsonify(
            {
                "code": ErrorCode.SUCCESS if success else 1,
                "message": "cancel requested" if success else "task not found or already finished",
                "trace_id": trace_id,
            }
        )

    @bp.route("/task_names", methods=["GET"])
    async def task_names():
        """返回所有已注册的任务名，供前端下拉框使用。"""
        from src.jobs.task_handler import TaskHandler

        names = TaskHandler.list_registered_tasks()
        return jsonify({"code": 0, "data": sorted(names)})

    @bp.route("/tasks", methods=["GET"])
    async def list_tasks():
        args = request.args
        status_filter = args.getlist("status")
        task_name = args.get("task_name")
        date = args.get("date")
        trace_id_q = args.get("trace_id")
        try:
            page = max(1, int(args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(1, int(args.get("page_size", 20))), 100)
        except (TypeError, ValueError):
            page_size = 20

        filter_sql, filter_params = _build_tasks_filter(
            status_filter, task_name, date, trace_id_q
        )

        total_row = await deps.mysql.async_fetch_one(
            f"SELECT COUNT(*) AS c FROM task_manager {filter_sql}",
            params=filter_params,
        )
        total = total_row["c"] if total_row else 0

        items = await deps.mysql.async_fetch(
            f"SELECT * FROM task_manager {filter_sql} "
            "ORDER BY start_timestamp DESC LIMIT %s OFFSET %s",
            params=(*filter_params, page_size, (page - 1) * page_size),
        )
        items = decode_json_columns(items, ["data"], default={})

        return jsonify(
            {
                "code": 0,
                "data": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "items": items,
                },
            }
        )

    @bp.route("/tasks/<trace_id>", methods=["GET"])
    async def get_task(trace_id: str):
        task = await deps.mysql.async_fetch_one(
            "SELECT * FROM task_manager WHERE trace_id = %s", params=(trace_id,)
        )
        if not task:
            return jsonify({"code": 404, "message": "task not found"}), 404
        task = decode_json_row(task, ["data"], default={})

        from src.api.v1.utils.agent_metadata import build_agent_metadata

        agent_meta = await build_agent_metadata(deps.mysql, trace_id)
        return jsonify(
            {
                "code": 0,
                "data": {**task, "agent_metadata": agent_meta},
            }
        )

    @bp.route("/tasks/<trace_id>/events", methods=["GET"])
    async def get_task_events(trace_id: str):
        rows = await deps.mysql.async_fetch(
            "SELECT sequence, event_type, source, step, payload, created_at "
            "FROM agent_events WHERE trace_id = %s ORDER BY sequence",
            params=(trace_id,),
        )
        closed = not deps.events.has_trace(trace_id) or deps.events.is_closed(trace_id)

        from src.api.v1.utils.agent_metadata import normalize_event

        return jsonify(
            {
                "code": 0,
                "data": {
                    "trace_id": trace_id,
                    "closed": closed,
                    "events": [normalize_event(r) for r in rows],
                },
            }
        )

    @bp.route("/task_events/<trace_id>", methods=["GET"])
    async def task_events(trace_id: str):
        if not deps.events.has_trace(trace_id):
            return jsonify({"code": 404, "message": "trace not found", "trace_id": trace_id}), 404

        last_event_id = request.headers.get("Last-Event-ID")
        after_sequence = None
        if last_event_id and str(last_event_id).isdigit():
            after_sequence = int(last_event_id)

        async def generate():
            subscription = deps.events.subscribe(trace_id, after_sequence=after_sequence)
            heartbeat_seconds = 15.0
            try:
                while True:
                    if deps.events.is_closed(trace_id) and subscription.queue.empty():
                        break
                    try:
                        event = await asyncio.wait_for(
                            subscription.queue.get(), timeout=heartbeat_seconds
                        )
                        yield (
                            f"id: {event['sequence']}\n"
                            f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        )
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                deps.events.unsubscribe(subscription)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return Response(generate(), mimetype="text/event-stream", headers=headers)

    return bp
