from __future__ import annotations

import json
from typing import Literal

from quart import Blueprint, jsonify

from src.api.v1.utils import ApiDependencies, decode_json_columns

HealthFlag = Literal["ok", "degraded", "failed", "stopped"]

_ERROR_KEYS = ("error", "error_message", "failure_reason", "reason")


def _extract_error(data_field) -> str | None:
    if data_field is None:
        return None
    if isinstance(data_field, str):
        try:
            data_field = json.loads(data_field)
        except json.JSONDecodeError:
            return data_field[:200]
    if not isinstance(data_field, dict):
        return None
    for key in _ERROR_KEYS:
        v = data_field.get(key)
        if v:
            return str(v)[:200]
    return None


async def _check_mysql(deps: ApiDependencies) -> HealthFlag:
    try:
        row = await deps.mysql.async_fetch_one("SELECT 1 AS ok")
        return "ok" if row else "degraded"
    except Exception:
        return "failed"


def _check_log_service(deps: ApiDependencies) -> HealthFlag:
    try:
        metrics = deps.log.get_metrics()
        return "ok" if metrics.get("is_running") else "stopped"
    except Exception:
        return "failed"


async def _hourly_throughput(deps: ApiDependencies, since_ts: int) -> list:
    rows = await deps.mysql.async_fetch(
        "SELECT FROM_UNIXTIME(start_timestamp, '%%H:00') AS hour, "
        "SUM(task_status=2) AS success, "
        "SUM(task_status=99) AS failed "
        "FROM task_manager WHERE start_timestamp > %s "
        "GROUP BY hour ORDER BY hour",
        params=(since_ts,),
    )
    return rows


async def _recent_failures(deps: ApiDependencies, limit: int = 10) -> list:
    rows = await deps.mysql.async_fetch(
        "SELECT * FROM task_manager WHERE task_status = 99 "
        "ORDER BY finish_timestamp DESC LIMIT %s",
        params=(limit,),
    )
    rows = decode_json_columns(rows, ["data"], default={})
    for row in rows:
        row["error"] = _extract_error(row.get("data"))
    return rows


def create_system_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("system", __name__)

    @bp.route("/system/stats", methods=["GET"])
    async def system_stats():
        import time

        now = int(time.time())
        since_ts = now - 86400

        mysql_flag = await _check_mysql(deps)
        log_flag = _check_log_service(deps)

        counts_row = await deps.mysql.async_fetch_one(
            "SELECT "
            "SUM(task_status=1 OR task_status=4) AS running, "
            "SUM(task_status=2 AND start_timestamp > %s) AS success_24h, "
            "SUM(task_status=99 AND start_timestamp > %s) AS failed_24h, "
            "SUM(task_status=3 AND start_timestamp > %s) AS cancelled_24h "
            "FROM task_manager",
            params=(since_ts, since_ts, since_ts),
        )

        throughput = await _hourly_throughput(deps, since_ts)
        failures = await _recent_failures(deps, limit=10)

        return jsonify(
            {
                "code": 0,
                "data": {
                    "health": {
                        "mysql": mysql_flag,
                        "log_service": log_flag,
                    },
                    "counts": {
                        "running": int(counts_row["running"] or 0),
                        "success_24h": int(counts_row["success_24h"] or 0),
                        "failed_24h": int(counts_row["failed_24h"] or 0),
                        "cancelled_24h": int(counts_row["cancelled_24h"] or 0),
                    },
                    "throughput_24h": throughput,
                    "recent_failures": failures,
                },
            }
        )

    return bp
