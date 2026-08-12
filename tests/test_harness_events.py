import json

import pytest

from src.core.agents.engine.loop import Act, Observe, Think
from src.core.agents.runtime.harness import AgentBudget, AgentLoopHarness
from src.core.agents.capabilities.skills import SkillExecutor, SkillRegistry


class RecordingEventBus:
    def __init__(self):
        self.events = []

    def publish(self, **event):
        json.dumps(event["data"])
        self.events.append(event)


@pytest.mark.asyncio
async def test_harness_publishes_json_safe_run_lifecycle():
    async def planner(_messages, _step, **_kwargs):
        return {"role": "assistant", "content": "done"}

    registry = SkillRegistry(namespace="events")
    bus = RecordingEventBus()
    harness = AgentLoopHarness(
        thinker=Think(planner),
        actor=Act(registry=registry, executor=SkillExecutor()),
        observer=Observe(),
        budget=AgentBudget(max_steps=2),
        event_bus=bus,
    )

    await harness.run(
        "finish",
        trace_id="trace-events",
        metadata={"attempt": 1},
    )

    event_types = [event["event_type"] for event in bus.events]
    assert event_types == [
        "run_start",
        "step_start",
        "prompt_assembled",
        "step_end",
        "improvement_recorded",
        "run_end",
        "turn_end",
    ]
    run_end = next(event for event in bus.events if event["event_type"] == "run_end")
    assert run_end["data"]["result"]["stop_reason"] == "model_final"
    assert run_end["data"]["result"]["metadata"]["attempt"] == 1
