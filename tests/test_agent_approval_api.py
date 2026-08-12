import json
from types import SimpleNamespace

import pytest
from quart import Quart

import src.api.v1.endpoints.agent as agent_endpoint
from src.infra.streaming import TraceEventBus
from src.jobs.task_config import TaskStatus


class FakeDatabase:
    def __init__(self, task):
        self.task = task
        self.updates = []

    async def async_fetch_one(self, query, params=None):
        if "MAX(sequence)" in query:
            return {"sequence": 11}
        return self.task

    async def async_save(self, query, params=None):
        self.updates.append((query, params))
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


def _task(request_id="apr-1"):
    return {
        "task_status": TaskStatus.WAITING_APPROVAL,
        "data": json.dumps(
            {
                "goal": "write",
                "tool_areas": ["task"],
                "max_steps": 8,
                "tool_policy": {
                    "allowed_risk_levels": ["read", "write"],
                    "allowed_tools": None,
                    "blocked_tools": [],
                },
                "approval_policy": {
                    "required_risk_levels": ["write", "destructive"],
                    "required_tools": [],
                    "exempt_tools": [],
                },
                "pending_approval": {"request_id": request_id},
                "checkpoint": {"schema_version": 3},
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
async def test_approval_endpoint_atomically_resumes_and_continues_event_sequence(monkeypatch):
    database = FakeDatabase(_task())
    app, events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/approval",
        json={"request_id": "apr-1", "decision": "approve", "actor_id": "forged"},
    )

    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["data"]["decision"] == "approve"
    assert len(database.updates) == 1
    update_params = database.updates[0][1]
    assert update_params[0] == TaskStatus.INIT
    resumed_data = json.loads(update_params[2])
    assert resumed_data["approval_decision"]["actor_id"] == "42"
    assert FakeScheduler.instances[0].data == resumed_data
    assert events._traces["trace-1"].sequence == 11
    assert not events.is_closed("trace-1")


@pytest.mark.asyncio
async def test_approval_endpoint_rejects_mismatched_request_without_state_change(monkeypatch):
    database = FakeDatabase(_task("apr-expected"))
    app, _events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/approval",
        json={"request_id": "apr-other", "decision": "reject"},
    )

    assert response.status_code == 400
    assert database.updates == []
    assert FakeScheduler.instances == []


@pytest.mark.asyncio
async def test_approval_endpoint_restores_waiting_state_when_scheduling_fails(monkeypatch):
    database = FakeDatabase(_task())
    app, events = _app(database)
    FailingScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FailingScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/approval",
        json={"request_id": "apr-1", "decision": "approve"},
    )

    assert response.status_code == 200
    assert len(database.updates) == 2
    rollback_params = database.updates[-1][1]
    assert rollback_params[0] == TaskStatus.WAITING_APPROVAL
    assert json.loads(rollback_params[2])["pending_approval"]["request_id"] == "apr-1"
    assert events.is_closed("trace-1")


@pytest.mark.asyncio
async def test_approval_endpoint_recovers_init_claim_after_process_crash(monkeypatch):
    task = _task()
    run_data = json.loads(task["data"])
    run_data.update(
        status="resuming",
        approval_decision={
            "request_id": "apr-1",
            "decision": "approve",
            "reason": None,
            "actor_id": "42",
        },
    )
    task["task_status"] = TaskStatus.INIT
    task["data"] = json.dumps(run_data)
    database = FakeDatabase(task)
    app, _events = _app(database)
    FakeScheduler.instances.clear()
    monkeypatch.setattr(agent_endpoint, "TaskScheduler", FakeScheduler)
    monkeypatch.setattr(agent_endpoint, "get_current_account_id", lambda: 42)

    response = await app.test_client().post(
        "/api/agent/runs/trace-1/approval",
        json={"request_id": "apr-1", "decision": "approve"},
    )

    assert response.status_code == 200
    assert FakeScheduler.instances[0].data == {**run_data, "task_name": "agent.run"}
