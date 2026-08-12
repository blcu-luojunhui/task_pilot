from types import SimpleNamespace

import pytest

from src.jobs.task_config import TaskStatus
from src.jobs.task_scheduler import TaskScheduler


class RecordingDatabase:
    def __init__(self):
        self.saved = []

    async def async_save(self, query, params=None):
        self.saved.append((query, params))
        return 1


class NullLog:
    async def log(self, contents):
        return None


@pytest.mark.asyncio
async def test_waiting_approval_task_can_be_cancelled_immediately():
    database = RecordingDatabase()
    deps = SimpleNamespace(
        log=NullLog(),
        db=database,
        config=SimpleNamespace(task_table="task_manager"),
        alert=None,
        lifecycle=None,
        events=None,
    )
    scheduler = TaskScheduler({}, "trace-waiting", deps, account_id=7)

    assert await scheduler.cancel_task()
    query, params = database.saved[0]

    assert "finish_timestamp = CASE" in query
    assert query.index("finish_timestamp = CASE") < query.index("task_status = CASE")
    assert params[:2] == (TaskStatus.INIT, TaskStatus.WAITING_APPROVAL)
    assert params[-5:-1] == (
        TaskStatus.INIT,
        TaskStatus.PROCESSING,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.WAITING_RECONCILIATION,
    )
