from __future__ import annotations

import asyncio
import json
from pydantic import ValidationError
from quart import Blueprint, Response, jsonify, current_app, request

from src.jobs import TaskScheduler
from src.api.v1.utils import ApiDependencies
from src.api.v1.utils import RunTaskRequest, CancelTaskRequest
from src.api.v1.utils import parse_json, validation_error_response
from src.api.middleware.trace import get_current_trace_id
from src.infra.shared import ErrorCode


def create_tasks_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("tasks", __name__)

    @bp.route("/run_task", methods=["POST"])
    async def run_task():
        if not current_app.config.get("ACCEPTING_TASKS", True):
            return jsonify({"code": ErrorCode.SERVICE_SHUTTING_DOWN, "message": "Server is shutting down"}), 503

        trace_id = get_current_trace_id()

        try:
            _, body = await parse_json(RunTaskRequest)
        except ValidationError as e:
            payload, status = validation_error_response(e)
            return jsonify(payload), status

        scheduler = TaskScheduler(body, trace_id, deps)
        result = await scheduler.deal()
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
                "message": "cancel requested"
                if success
                else "task not found or already finished",
                "trace_id": trace_id,
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
                        event = await asyncio.wait_for(subscription.queue.get(), timeout=heartbeat_seconds)
                        yield (
                            f"id: {event['sequence']}\n"
                            f"event: {event['type']}\n"
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
