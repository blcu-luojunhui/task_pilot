import json
from types import SimpleNamespace

import pytest
from quart import Quart

import src.api.v1.endpoints.agent as agent_endpoint
from src.infra.streaming import TraceEventBus
from src.jobs.task_config import TaskStatus


class ReconciliationDatabase:
    def __init__(self, task, *, cas_result=1, ledger_result=1):
        self.task = task
        self.cas_result = cas_result
        self.ledger_result = ledger_result
        self.updates = []
        self.ledger = {
            "status": "running",
            "result_content": None,
            "error_message": None,
        }

    async def async_fetch_one(self, query, params=None):
        if "MAX(sequence)" in query:
            return {"sequence": 17}
        if "FROM agent_tool_executions" in query:
            return dict(self.ledger)
        return self.task

    async def async_save(self, query, params=None):
        self.updates.append((query, params))
        if "UPDATE task_manager SET task_status" in query:
            result = self.cas_result
            self.cas_result = 1
            return result
        if query.startswith("UPDATE agent_tool_executions"):
            result = self.ledger_result
            if result:
                self.ledger.update(
                    status=params[0],
                    result_content=params[1],
                    error_message=params[2],
                )
            return result
        return 1


class FakeScheduler:
    instances = []

    def __init__(self, data, trace_id, deps, account_id=0):
        self.data = data
        self.trace_id = trace_id
        self.account_id = account_id
        self.__class__.instances.append(self)

    async def deal(self):
        return {"code": 0, "data": {"trace_id": self.trace_id}}


class FailingScheduler(FakeScheduler):
    async def deal(self):
        return {"code": 5005, "message": "concurrency limit"}


def _task(call_id="call-1"):
    return {
        "task_status": TaskStatus.WAITING_RECONCILIATION,
        "data": json.dumps(
            {
                "goal": "write",
                "tool_areas": ["task"],
                "pending_reconciliation": {
                    "tool_call_id": call_id,
                    "tool_name": "write_once",
                    "arguments": {"token": "[REDACTED]"},
                },
                "checkpoint": {"schema_version": 4},
            }
        ),
    }


def _app(database):
    app = Quart(__name__)
    events = TraceEventBus()
    deps = SimpleNamespace(mysql=database, events=events)
    app.register_blueprint(agent_endpoint.create_agent_bp(deps), url_prefix="/api")
    return app, events


@pytest.mark.asyncio
async def test_reconciliation_endpoint_atomically_resolves_ledger_and_resumes(monkeypatch):
    database = ReconciliationDatabase(_task())
    app, events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/reconciliation",
        json={
            "tool_call_id": "call-1",
            "decision": "completed",
            "result_content": "saved with api_key=secret-value",
            "actor_id": "forged",
        },
    )

    assert response.status_code == 200
    resumed = FakeScheduler.instances[0].data
    decision = resumed["reconciliation_decision"]
    assert decision["actor_id"] == "42"
    assert "secret-value" not in decision["result_content"]
    assert database.ledger["status"] == "completed"
    assert events._traces["trace-1"].sequence == 17


@pytest.mark.asyncio
async def test_reconciliation_endpoint_rejects_call_mismatch_without_state_change(monkeypatch):
    database = ReconciliationDatabase(_task("call-expected"))
    app, _events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/reconciliation",
        json={"tool_call_id": "call-other", "decision": "failed"},
    )

    assert response.status_code == 400
    assert database.updates == []
    assert FakeScheduler.instances == []


@pytest.mark.asyncio
async def test_reconciliation_endpoint_returns_conflict_when_cas_loses(monkeypatch):
    database = ReconciliationDatabase(_task(), cas_result=0)
    app, _events = _app(database)
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/reconciliation",
        json={"tool_call_id": "call-1", "decision": "failed"},
    )

    assert response.status_code == 409
    assert database.ledger["status"] == "failed"


@pytest.mark.asyncio
async def test_reconciliation_endpoint_recovers_init_claim_after_process_crash(monkeypatch):
    task = _task()
    run_data = json.loads(task["data"])
    run_data.update(
        status="resuming",
        reconciliation_decision={
            "tool_call_id": "call-1",
            "decision": "failed",
            "result_content": None,
            "reason": "confirmed absent",
            "actor_id": "42",
        },
    )
    task["task_status"] = TaskStatus.INIT
    task["data"] = json.dumps(run_data)
    database = ReconciliationDatabase(task, ledger_result=0)
    database.ledger.update(
        status="failed",
        error_message="confirmed absent",
    )
    app, _events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/reconciliation",
        json={
            "tool_call_id": "call-1",
            "decision": "failed",
            "reason": "confirmed absent",
        },
    )

    assert response.status_code == 200
    assert FakeScheduler.instances[0].data == {**run_data, "task_name": "agent.run"}


@pytest.mark.asyncio
async def test_reconciliation_endpoint_restores_waiting_when_scheduling_fails(monkeypatch):
    database = ReconciliationDatabase(_task())
    app, events = _app(database)
    FailingScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FailingScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/reconciliation",
        json={
            "tool_call_id": "call-1",
            "decision": "failed",
            "reason": "confirmed absent",
        },
    )

    assert response.status_code == 200
    rollback_params = database.updates[-1][1]
    assert rollback_params[0] == TaskStatus.WAITING_RECONCILIATION
    assert json.loads(rollback_params[2])["pending_reconciliation"]["tool_call_id"] == "call-1"
    assert events.is_closed("trace-1")
