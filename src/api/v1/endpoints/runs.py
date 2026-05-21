"""
Runs API — 查询历史 Agent 运行记录（agent_run_summaries 表）
"""
from __future__ import annotations

from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies, decode_json_columns


def create_runs_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("runs", __name__)

    @bp.route("/runs", methods=["GET"])
    async def list_runs():
        args = request.args
        try:
            page = max(1, int(args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(1, int(args.get("page_size", 20))), 100)
        except (TypeError, ValueError):
            page_size = 20

        conditions = []
        params = []

        success_filter = args.get("success")
        if success_filter is not None:
            conditions.append("success = %s")
            params.append(int(success_filter))

        goal_keyword = args.get("goal_keyword")
        if goal_keyword:
            conditions.append("goal LIKE %s")
            escaped = goal_keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")

        trace_id_q = args.get("trace_id")
        if trace_id_q:
            conditions.append("trace_id LIKE %s")
            params.append(f"%{trace_id_q}%")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        total_row = await deps.mysql.async_fetch_one(
            f"SELECT COUNT(*) AS c FROM agent_run_summaries {where}", params=params
        )
        total = total_row["c"] if total_row else 0

        items = await deps.mysql.async_fetch(
            f"SELECT * FROM agent_run_summaries {where} "
            "ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params=(*params, page_size, (page - 1) * page_size),
        )
        items = decode_json_columns(
            items,
            ["token_usage", "failed_tool_calls", "metadata"],
            default=None,
        )

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

    return bp
