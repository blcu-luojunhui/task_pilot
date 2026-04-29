from prometheus_client import Counter, Gauge, Histogram

# HTTP 指标
http_requests_total = Counter(
    "taskpilot_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "taskpilot_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

# Task 指标
tasks_started_total = Counter(
    "taskpilot_tasks_started_total",
    "Total tasks started",
    ["task_name"],
)

tasks_completed_total = Counter(
    "taskpilot_tasks_completed_total",
    "Total tasks completed",
    ["task_name", "status"],
)

# 服务队列指标
log_queue_size = Gauge(
    "taskpilot_log_queue_size",
    "Current log queue size",
)

log_dropped_total = Counter(
    "taskpilot_log_dropped_total",
    "Total dropped logs",
)

alert_queue_size = Gauge(
    "taskpilot_alert_queue_size",
    "Current alert queue size",
)

alert_dropped_total = Counter(
    "taskpilot_alert_dropped_total",
    "Total dropped alerts",
)
