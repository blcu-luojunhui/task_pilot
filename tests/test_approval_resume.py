import pytest

from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillExecutor, SkillRegistry
from src.core.agents.engine.loop import Act, Observe, Think
from src.core.agents.runtime.harness import (
    AgentBudget,
    AgentLoopHarness,
    ApprovalDecision,
    ApprovalPolicy,
)
from src.core.agents.state import AgentState, StateSnapshot, StopReason


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
                    "arguments": '{"value": "approved"}',
                },
            }
        ],
    }


def _build_harness(planner, handler, events=None):
    registry = SkillRegistry(namespace="approval")
    registry.register(
        Skill.executable(
            name="write_record",
            description="write",
            handler=handler,
            parameters={"value": {"type": "string", "required": True}},
            risk_level=RiskLevel.WRITE,
        )
    )
    return AgentLoopHarness(
        thinker=Think(planner),
        actor=Act(registry=registry, executor=SkillExecutor()),
        observer=Observe(),
        budget=AgentBudget(max_steps=4),
        approval_policy=ApprovalPolicy(),
        event_bus=events,
    )


class RecordingEventBus:
    def __init__(self):
        self.events = []

    def publish(self, **event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_write_tool_pauses_before_side_effect():
    executed = []
    events = RecordingEventBus()

    async def planner(_messages, _step, **_kwargs):
        return _tool_call()

    async def handler(_ctx, value):
        executed.append(value)
        return "ok"

    harness = _build_harness(planner, handler, events)
    result = await harness.run("write", trace_id="trace-approval")

    assert result.stop_reason == StopReason.APPROVAL_REQUIRED
    assert result.pending_approval["tool_calls"][0]["tool_name"] == "write_record"
    assert executed == []
    assert harness._current_state.messages == []
    event_types = [event["event_type"] for event in events.events]
    assert "approval_required" in event_types
    assert "run_paused" in event_types
    assert "turn_paused" in event_types
    assert "run_end" not in event_types
    assert "turn_end" not in event_types


@pytest.mark.asyncio
async def test_approved_checkpoint_executes_frozen_call_without_regenerating(tmp_path):
    planner_calls = 0
    executed = []

    async def planner(_messages, _step, **_kwargs):
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls == 1:
            return _tool_call()
        return {"role": "assistant", "content": "done"}

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    harness = _build_harness(planner, handler)
    paused = await harness.run("write", trace_id="trace-resume")
    state = harness._current_state
    request_id = paused.pending_approval["request_id"]

    snapshots = StateSnapshot(tmp_path)
    snapshot_id = snapshots.save("trace-resume", state, AgentState.PAUSED)
    restored, _lifecycle, _metadata = snapshots.load(snapshot_id)

    resumed = await harness.run(
        restored.goal,
        trace_id=restored.trace_id,
        initial_state=restored,
        approval_decision=ApprovalDecision(request_id, "approve", actor_id="user-1"),
    )

    assert resumed.success
    assert resumed.final_answer == "done"
    assert planner_calls == 2
    assert executed == ["approved"]
    assert restored.step == 2
    assert restored.metadata["approval_history"][0]["actor_id"] == "user-1"


@pytest.mark.asyncio
async def test_rejected_checkpoint_returns_tool_error_to_model():
    seen_messages = []
    executed = []

    async def planner(messages, _step, **_kwargs):
        seen_messages.append(messages)
        if len(seen_messages) == 1:
            return _tool_call()
        return {"role": "assistant", "content": "request was rejected"}

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    harness = _build_harness(planner, handler)
    paused = await harness.run("write", trace_id="trace-reject")
    state = harness._current_state
    result = await harness.run(
        state.goal,
        trace_id=state.trace_id,
        initial_state=state,
        approval_decision=ApprovalDecision(
            paused.pending_approval["request_id"],
            "reject",
            reason="not authorized",
        ),
    )

    assert result.success
    assert executed == []
    assert any(
        message.get("role") == "tool" and "not authorized" in message.get("content", "")
        for message in seen_messages[-1]
    )


@pytest.mark.asyncio
async def test_rejection_reason_is_redacted_before_model_feedback():
    seen_messages = []

    async def planner(messages, _step, **_kwargs):
        seen_messages.append(messages)
        if len(seen_messages) == 1:
            return _tool_call()
        return {"role": "assistant", "content": "rejected safely"}

    async def handler(_ctx, value):
        raise AssertionError(value)

    harness = _build_harness(planner, handler)
    paused = await harness.run("write", trace_id="trace-redacted-reject")
    result = await harness.run(
        harness._current_state.goal,
        trace_id="trace-redacted-reject",
        initial_state=harness._current_state,
        approval_decision=ApprovalDecision(
            paused.pending_approval["request_id"],
            "reject",
            reason="blocked because api_key=secret-value",
        ),
    )

    assert result.success
    tool_message = next(
        message for message in seen_messages[-1] if message.get("role") == "tool"
    )
    assert "secret-value" not in tool_message["content"]
    assert "[REDACTED]" in tool_message["content"]
