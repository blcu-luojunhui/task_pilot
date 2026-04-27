from __future__ import annotations

from pydantic import ValidationError
from quart import Blueprint, jsonify, current_app

from src.api.service import TaskScheduler
from src.api.v1.utils import ApiDependencies
from src.api.v1.utils import RunTaskRequest, CancelTaskRequest
from src.api.v1.utils import parse_json, validation_error_response
from src.shared.tools import generate_task_trace_id


def create_tasks_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("tasks", __name__)

    @bp.route("/run_task", methods=["POST"])
    async def run_task():
        if not current_app.config.get("ACCEPTING_TASKS", True):
            return jsonify({"code": 5003, "message": "Server is shutting down"}), 503

        trace_id = generate_task_trace_id()

        try:
            _, body = await parse_json(RunTaskRequest)
        except ValidationError as e:
            payload, status = validation_error_response(e)
            return jsonify(payload), status

        scheduler = TaskScheduler(body, deps.log, deps.db, trace_id, deps.config)
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
        scheduler = TaskScheduler(body, deps.log, deps.db, trace_id, deps.config)
        success = await scheduler.cancel_task(trace_id)

        return jsonify(
            {
                "code": 0 if success else 1,
                "message": "cancel requested" if success else "task not found or already finished",
                "trace_id": trace_id,
            }
        )

    return bp
