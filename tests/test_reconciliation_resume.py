import pytest

from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillExecutor, SkillRegistry
from src.core.agents.engine.loop import Act, Observe, Think
from src.core.agents.execution import DBToolExecutionLedger
from src.core.agents.runtime.harness import (
    AgentBudget,
    AgentLoopHarness,
    ReconciliationDecision,
)
from src.core.agents.state import AgentState, StateSnapshot, StopReason

from test_execution_ledger import MemoryLedgerDatabase


def _tool_call():
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-write-1",
                "type": "function",
                "function": {
                    "name": "write_record",
                    "arguments": '{"value":"frozen"}',
                },
            }
        ],
    }


def _harness(planner, database, events=None):
    registry = SkillRegistry(namespace="reconciliation")

    async def handler(_ctx, value):
        raise AssertionError(f"ambiguous call must not execute again: {value}")

    registry.register(
        Skill.executable(
            name="write_record",
            description="write",
            handler=handler,
            risk_level=RiskLevel.WRITE,
            parameters={"value": {"type": "string", "required": True}},
        )
    )
    return AgentLoopHarness(
        thinker=Think(planner),
        actor=Act(
            registry=registry,
            executor=SkillExecutor(),
            execution_ledger=DBToolExecutionLedger(database),
        ),
        observer=Observe(),
        budget=AgentBudget(max_steps=4),
        event_bus=events,
    )


class RecordingEventBus:
    def __init__(self):
        self.events = []

    def publish(self, **event):
        self.events.append(event)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "result_content", "expected"),
    [
        ("completed", "verified downstream", "verified downstream"),
        ("failed", None, "confirmed absent"),
    ],
)
async def test_reconciliation_checkpoint_resumes_without_reexecuting(
    tmp_path,
    decision,
    result_content,
    expected,
):
    database = MemoryLedgerDatabase()
    await DBToolExecutionLedger(database).claim(
        "trace-reconcile",
        "call-write-1",
        "write_record",
        {"value": "frozen"},
    )
    seen_messages = []

    async def planner(messages, _step, **_kwargs):
        seen_messages.append(messages)
        if len(seen_messages) == 1:
            return _tool_call()
        return {"role": "assistant", "content": "done"}

    events = RecordingEventBus()
    harness = _harness(planner, database, events)
    paused = await harness.run("write", trace_id="trace-reconcile")

    assert paused.stop_reason == StopReason.EXECUTION_IN_DOUBT
    assert paused.pending_reconciliation["tool_call_id"] == "call-write-1"
    event_types = [event["event_type"] for event in events.events]
    assert "reconciliation_required" in event_types
    assert "run_paused" in event_types
    assert "run_end" not in event_types

    snapshot_id = StateSnapshot(tmp_path).save(
        "trace-reconcile",
        harness._current_state,
        AgentState.PAUSED,
    )
    restored, _lifecycle, _metadata = StateSnapshot(tmp_path).load(snapshot_id)
    resumed = await harness.run(
        restored.goal,
        trace_id=restored.trace_id,
        initial_state=restored,
        reconciliation_decision=ReconciliationDecision(
            "call-write-1",
            decision,
            result_content=result_content,
            reason="confirmed absent" if decision == "failed" else "verified",
            actor_id="operator-1",
        ),
    )

    assert resumed.success
    assert resumed.final_answer == "done"
    assert resumed.metadata["reconciliation_history"][0]["actor_id"] == "operator-1"
    assert resumed.metadata["reconciliation_history"][0]["result_digest"] is not None if result_content else True
    assert any(
        message.get("role") == "tool" and expected in message.get("content", "")
        for message in seen_messages[-1]
    )
