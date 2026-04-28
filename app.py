import logging
from quart_cors import cors
from quart import Quart

from src.core.bootstrap import AppContext
from src.core.dependency import ServerContainer
from src.api.v1.routes import server_routes
from src.jobs.task_lifecycle import TaskLifecycleManager
from src.infra.observability import AlertService

logging.basicConfig(level=logging.INFO)

app = Quart(__name__)
app = cors(app, allow_origin="*")
app.config["ACCEPTING_TASKS"] = True

server_container = ServerContainer()
ctx = AppContext(server_container)

config = server_container.config()
log_service = server_container.log_service()
async_mysql_pool = server_container.async_mysql_pool()

routes = server_routes(async_mysql_pool, log_service, config)
app.register_blueprint(routes)


@app.before_serving
async def startup():
    logging.info("Starting TaskPilot...")
    await ctx.start_up()

    alert_service = AlertService.initialize()
    await alert_service.start()

    lifecycle = TaskLifecycleManager.initialize(async_mysql_pool, poll_interval=5.0)
    await lifecycle.start_polling()

    logging.info("TaskPilot started successfully")


@app.after_serving
async def shutdown():
    logging.info("Shutting down TaskPilot...")

    app.config["ACCEPTING_TASKS"] = False
    logging.info("Phase 1: Stopped accepting new tasks")

    lifecycle = TaskLifecycleManager.get_instance()
    if lifecycle:
        await lifecycle.shutdown(timeout=30.0)
    logging.info("Phase 2: All tasks cancelled/completed")

    alert_service = AlertService.get_instance()
    if alert_service:
        await alert_service.stop(drain_timeout=5.0)

    await log_service.stop(drain_timeout=10.0)
    logging.info("Phase 3: Alerts and logs flushed")

    await ctx.shutdown()
    logging.info("Phase 4: Database pools closed")

    logging.info("TaskPilot shutdown complete")
