from types import SimpleNamespace

import pytest

from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillExecutor, SkillRegistry
from src.core.agents.engine.agent import Agent, AgentConfig
from src.core.agents.engine.lifecycle import LifecycleManager
from src.core.agents.engine.runner import AgentLoopRunner
from src.core.agents.exceptions import AgentConfigError
from src.core.agents.runtime.harness import ApprovalPolicy
from src.core.agents.state import AgentState, StateSnapshot, StopReason


def _tool_call():
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-sdk-1",
                "type": "function",
                "function": {
                    "name": "write_sdk",
                    "arguments": '{"value":"frozen"}',
                },
            }
        ],
    }


def _build_agent(planner, handler):
    registry = SkillRegistry(namespace="sdk-snapshot")
    registry.register(
        Skill.executable(
            name="write_sdk",
            description="write",
            handler=handler,
            risk_level=RiskLevel.WRITE,
            parameters={"value": {"type": "string", "required": True}},
        )
    )
    lifecycle = LifecycleManager()
    config = AgentConfig(llm_api_key="test", max_steps=4, approval_policy=ApprovalPolicy())
    runner = AgentLoopRunner(
        planner=planner,
        registry=registry,
        executor=SkillExecutor(),
        max_steps=4,
        lifecycle=lifecycle,
        approval_policy=config.approval_policy,
    )
    return Agent(
        runner,
        registry,
        config,
        provider=SimpleNamespace(),
        lifecycle=lifecycle,
    )


@pytest.mark.asyncio
async def test_sdk_snapshot_requires_decision_and_resumes_approved_call(tmp_path):
    planner_calls = 0
    executed = []

    async def planner(_messages, _step, **_kwargs):
        nonlocal planner_calls
        planner_calls += 1
        return _tool_call() if planner_calls == 1 else {"role": "assistant", "content": "done"}

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    first_agent = _build_agent(planner, handler)
    paused = await first_agent.run("write")
    assert paused.stop_reason == StopReason.APPROVAL_REQUIRED
    state = first_agent._runner.harness._current_state
    snapshot_id = StateSnapshot(tmp_path).save(
        state.trace_id,
        state,
        AgentState.PAUSED,
    )

    restored_agent = _build_agent(planner, handler)
    with pytest.raises(AgentConfigError, match="approval_decision is required"):
        await restored_agent.run_from_snapshot(snapshot_id, snapshot_dir=tmp_path)

    result = await restored_agent.run_from_snapshot(
        snapshot_id,
        snapshot_dir=tmp_path,
        approval_decision={
            "request_id": paused.pending_approval["request_id"],
            "decision": "approve",
            "actor_id": "sdk-user",
        },
    )

    assert result.success
    assert result.final_answer == "done"
    assert executed == ["frozen"]
    assert planner_calls == 2
