import asyncio
import json
from types import SimpleNamespace

import pytest

import src.core.agent_task.run_goal as run_goal
from src.core.agents.capabilities.llm.base import FinishReason, LLMResponse
from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillRegistry
from src.jobs.task_config import TaskStatus


class RecordingDatabase:
    def __init__(self):
        self.saved_payloads = []
        self.ledger_rows = {}

    async def async_save(self, query, params=None, **_kwargs):
        if "UPDATE task_manager SET data" in query:
            self.saved_payloads.append(json.loads(params[0]))
        elif query.startswith("INSERT IGNORE INTO agent_tool_executions"):
            trace_id, call_id, tool_name, digest, account_id = params
            key = (trace_id, call_id, account_id)
            if key in self.ledger_rows:
                return 0
            self.ledger_rows[key] = {
                "tool_name": tool_name,
                "arguments_digest": digest,
                "status": "running",
                "result_content": None,
                "error_message": None,
            }
        elif query.startswith("UPDATE agent_tool_executions"):
            status, result, error, trace_id, call_id, account_id = params
            self.ledger_rows[(trace_id, call_id, account_id)].update(
                status=status,
                result_content=result,
                error_message=error,
            )
        return 1

    async def async_fetch_one(self, _query, params=None):
        return self.ledger_rows.get(tuple(params))


class FakeProvider:
    name = "openai"
    supports_streaming = False

    def __init__(self):
        self.config = SimpleNamespace(temperature=0.2)
        self.calls = 0

    async def chat(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call-write-1",
                        "type": "function",
                        "function": {
                            "name": "write_once",
                            "arguments": '{"value":"frozen"}',
                        },
                    }
                ],
                finish_reason=FinishReason.TOOL_CALLS,
            )
        return LLMResponse(content="completed", finish_reason=FinishReason.STOP)

    async def close(self):
        return None


class FakeEvents:
    def __init__(self):
        self.events = []

    def publish(self, **event):
        self.events.append(event)


def _scheduler(database, events):
    return SimpleNamespace(
        config=SimpleNamespace(
            llm=SimpleNamespace(max_steps=4, max_retries=0, retry_backoff_seconds=0),
        ),
        trace_id="trace-durable",
        account_id=7,
        db_client=database,
        log_service=SimpleNamespace(),
        lifecycle=None,
        events=events,
        alert_service=None,
    )


def _poll_task():
    async def wait_forever():
        await asyncio.Event().wait()

    return asyncio.create_task(wait_forever())


@pytest.mark.asyncio
async def test_agent_waits_persists_and_resumes_frozen_write(monkeypatch):
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    registry = SkillRegistry(namespace="durable")
    registry.register(
        Skill.executable(
            name="write_once",
            description="write once",
            handler=handler,
            domain="task",
            risk_level=RiskLevel.WRITE,
            parameters={"value": {"type": "string", "required": True}},
        )
    )
    monkeypatch.setattr(run_goal, "load_agentic_tools", lambda _areas: None)
    monkeypatch.setattr(run_goal, "get_global_registry", lambda: registry)

    database = RecordingDatabase()
    events = FakeEvents()
    scheduler = _scheduler(database, events)
    provider = FakeProvider()
    base_data = {
        "task_name": "agent.run",
        "goal": "persist a value",
        "tool_areas": ["task"],
        "max_steps": 4,
        "tool_policy": {
            "allowed_risk_levels": ["read", "write"],
            "allowed_tools": ["write_once"],
            "blocked_tools": [],
        },
        "approval_policy": {
            "required_risk_levels": ["write"],
            "required_tools": [],
            "exempt_tools": [],
        },
    }

    first_status = await run_goal._run_agent_mode(
        scheduler,
        base_data,
        provider,
        events,
        scheduler.trace_id,
        {"requested": False, "stop": False},
        _poll_task(),
        lambda: False,
    )

    waiting = database.saved_payloads[-1]
    assert first_status == TaskStatus.WAITING_APPROVAL
    assert waiting["status"] == "waiting_approval"
    assert executed == []

    resumed_data = {
        **waiting,
        "task_name": "agent.run",
        "approval_decision": {
            "request_id": waiting["pending_approval"]["request_id"],
            "decision": "approve",
            "actor_id": "7",
        },
    }
    second_status = await run_goal._run_agent_mode(
        scheduler,
        resumed_data,
        provider,
        events,
        scheduler.trace_id,
        {"requested": False, "stop": False},
        _poll_task(),
        lambda: False,
    )

    assert second_status == TaskStatus.SUCCESS
    assert executed == ["frozen"]
    assert provider.calls == 2
    assert database.ledger_rows[(scheduler.trace_id, "call-write-1", 7)]["status"] == "completed"
    assert database.saved_payloads[-1]["status"] == "completed"
    assert database.saved_payloads[-1]["approval_history"][0]["actor_id"] == "7"


@pytest.mark.asyncio
async def test_agent_persists_and_resumes_reconciled_write_without_reexecution(monkeypatch):
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "should not execute"

    registry = SkillRegistry(namespace="durable-reconciliation")
    registry.register(
        Skill.executable(
            name="write_once",
            description="write once",
            handler=handler,
            domain="task",
            risk_level=RiskLevel.WRITE,
            parameters={"value": {"type": "string", "required": True}},
        )
    )
    monkeypatch.setattr(run_goal, "load_agentic_tools", lambda _areas: None)
    monkeypatch.setattr(run_goal, "get_global_registry", lambda: registry)

    database = RecordingDatabase()
    events = FakeEvents()
    scheduler = _scheduler(database, events)
    provider = FakeProvider()
    base_data = {
        "task_name": "agent.run",
        "goal": "persist a value",
        "tool_areas": ["task"],
        "max_steps": 4,
        "tool_policy": {
            "allowed_risk_levels": ["read", "write"],
            "allowed_tools": ["write_once"],
            "blocked_tools": [],
        },
        "approval_policy": {
            "required_risk_levels": [],
            "required_tools": [],
            "exempt_tools": [],
        },
    }
    from src.core.agents.execution import DBToolExecutionLedger

    await DBToolExecutionLedger(database, account_id=7).claim(
        scheduler.trace_id,
        "call-write-1",
        "write_once",
        {"value": "frozen"},
    )

    first_status = await run_goal._run_agent_mode(
        scheduler,
        base_data,
        provider,
        events,
        scheduler.trace_id,
        {"requested": False, "stop": False},
        _poll_task(),
        lambda: False,
    )

    waiting = database.saved_payloads[-1]
    assert first_status == TaskStatus.WAITING_RECONCILIATION
    assert waiting["status"] == "waiting_reconciliation"
    assert waiting["pending_reconciliation"]["tool_call_id"] == "call-write-1"
    assert executed == []

    resumed_data = {
        **waiting,
        "task_name": "agent.run",
        "reconciliation_decision": {
            "tool_call_id": "call-write-1",
            "decision": "completed",
            "result_content": "verified saved value",
            "reason": "checked downstream",
            "actor_id": "7",
        },
    }
    second_status = await run_goal._run_agent_mode(
        scheduler,
        resumed_data,
        provider,
        events,
        scheduler.trace_id,
        {"requested": False, "stop": False},
        _poll_task(),
        lambda: False,
    )

    assert second_status == TaskStatus.SUCCESS
    assert executed == []
    assert provider.calls == 2
    assert database.saved_payloads[-1]["status"] == "completed"
    history = database.saved_payloads[-1]["reconciliation_history"]
    assert history[0]["actor_id"] == "7"
    assert history[0]["result_digest"]
