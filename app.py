import logging
import os
from quart_cors import cors
from quart import Quart, send_from_directory

from src.core.bootstrap import AppContext
from src.core.dependency import ServerContainer
from src.api.v1.routes import server_routes
from src.api.middleware import (
    TraceMiddleware,
    ErrorHandlerMiddleware,
    RequestLoggerMiddleware,
    RateLimitMiddleware,
)
from src.infra.observability import TraceIdFilter

# 配置日志格式，包含 trace_id
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(trace_id)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 为所有 logger 添加 TraceIdFilter
trace_filter = TraceIdFilter()
for handler in logging.root.handlers:
    handler.addFilter(trace_filter)

app = Quart(__name__)
app = cors(app, allow_origin="*")
app.config["ACCEPTING_TASKS"] = True
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB

# 注册中间件（顺序很重要）
TraceMiddleware(app)
ErrorHandlerMiddleware(app)
RequestLoggerMiddleware(app)
RateLimitMiddleware(
    app,
    max_requests=60,
    window_seconds=60,
    rate_limit_paths={"/api/run_task", "/api/cancel_task"},
)

server_container = ServerContainer()
ctx = AppContext(server_container)

config = server_container.config()
log_service = server_container.log_service()
alert_service = server_container.alert_service()
async_mysql_pool = server_container.async_mysql_pool()
lifecycle = server_container.task_lifecycle_manager()
events = server_container.trace_event_bus()

routes = server_routes(
    async_mysql_pool,
    log_service,
    config,
    alert_service,
    lifecycle,
    events,
)
app.register_blueprint(routes)

# ── Frontend SPA 静态托管 ──────────────────────────────────────────
_FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(__file__), "frontend", "dist"),
)
_FRONTEND_ENABLED = os.environ.get("FRONTEND_DIST_ENABLED", "true").lower() not in ("0", "false", "no")


def _static_enabled() -> bool:
    return _FRONTEND_ENABLED and os.path.isdir(_FRONTEND_DIST)


@app.route("/")
async def frontend_index():
    if not _static_enabled():
        return "Frontend not built — run `npm run build` in frontend/", 503
    return await send_from_directory(_FRONTEND_DIST, "index.html")


@app.route("/assets/<path:filename>")
async def frontend_assets(filename: str):
    if not _static_enabled():
        return "", 404
    return await send_from_directory(_FRONTEND_DIST, f"assets/{filename}")


@app.route("/<path:path>")
async def frontend_spa(path: str):
    if not _static_enabled():
        return "", 404
    full = os.path.join(_FRONTEND_DIST, path)
    if os.path.isfile(full):
        return await send_from_directory(_FRONTEND_DIST, path)
    return await send_from_directory(_FRONTEND_DIST, "index.html")


@app.before_serving
async def startup():
    logging.info("Starting TaskPilot...")
    await ctx.start_up()
    logging.info("TaskPilot started successfully")


@app.after_serving
async def shutdown():
    logging.info("Shutting down TaskPilot...")
    app.config["ACCEPTING_TASKS"] = False
    await ctx.shutdown()
    logging.info("TaskPilot shutdown complete")
