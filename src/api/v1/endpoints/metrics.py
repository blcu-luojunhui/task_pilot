from __future__ import annotations

from quart import Blueprint, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from src.api.v1.utils import ApiDependencies
from src.infra.observability import metrics


def create_metrics_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("metrics", __name__)

    @bp.route("/metrics", methods=["GET"])
    async def prometheus_metrics():
        """
        Prometheus metrics 端点

        暴露应用运行时指标
        """
        # 更新队列指标
        log_metrics = deps.log.get_metrics()
        metrics.log_queue_size.set(log_metrics["queue_size"])
        # Counter 只能递增，这里用 _value 直接设置是 hack，生产环境应该用 inc()
        # 但为了简化演示，这里直接同步
        if hasattr(metrics.log_dropped_total, "_value"):
            metrics.log_dropped_total._value._value = log_metrics["dropped_count"]

        alert_metrics = deps.alert.get_metrics()
        metrics.alert_queue_size.set(alert_metrics["queue_size"])
        if hasattr(metrics.alert_dropped_total, "_value"):
            metrics.alert_dropped_total._value._value = alert_metrics["dropped_count"]

        # 生成 Prometheus 格式输出
        output = generate_latest()
        return Response(output, mimetype=CONTENT_TYPE_LATEST)

    return bp
