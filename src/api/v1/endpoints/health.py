from __future__ import annotations

from quart import Blueprint, jsonify


def create_health_bp() -> Blueprint:
    bp = Blueprint("health", __name__)

    @bp.route("/health", methods=["GET"])
    async def health():
        return jsonify(
            {
                "code": 0,
                "message": "success",
                "data": {"message": "TaskPilot is running"},
            }
        )

    return bp
