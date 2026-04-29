from __future__ import annotations

import logging
from quart import Blueprint, jsonify

from src.api.v1.utils import ApiDependencies
from src.infra.shared import ErrorCode

logger = logging.getLogger(__name__)


def create_health_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("health", __name__)

    @bp.route("/health", methods=["GET"])
    async def health():
        """
        健康检查接口

        检查应用状态和 MySQL 连接池可用性
        """
        health_status = {
            "status": "healthy",
            "checks": {},
        }
        status_code = 200

        # 检查 MySQL 连接池
        try:
            result = await deps.mysql.async_fetch_one("SELECT 1 as health_check")
            if result and result.get("health_check") == 1:
                health_status["checks"]["mysql"] = "ok"
            else:
                health_status["checks"]["mysql"] = "degraded"
                health_status["status"] = "degraded"
                status_code = 503
        except Exception as e:
            logger.error(f"MySQL health check failed: {e}")
            health_status["checks"]["mysql"] = "failed"
            health_status["status"] = "unhealthy"
            status_code = 503

        # 检查日志服务
        try:
            metrics = deps.log.get_metrics()
            if metrics["is_running"]:
                health_status["checks"]["log_service"] = "ok"
            else:
                health_status["checks"]["log_service"] = "stopped"
                health_status["status"] = "degraded"
        except Exception as e:
            logger.error(f"Log service health check failed: {e}")
            health_status["checks"]["log_service"] = "unknown"

        return (
            jsonify(
                {
                    "code": ErrorCode.SUCCESS if status_code == 200 else ErrorCode.INTERNAL_ERROR,
                    "message": "success" if status_code == 200 else "unhealthy",
                    "data": health_status,
                }
            ),
            status_code,
        )

    return bp
