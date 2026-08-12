import pytest

from src.core.agents.capabilities.llm.base import FinishReason, LLMResponse
from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillRegistry
from src.core.agents.engine.agent import Agent, AgentConfig


async def _handler(_ctx):
    return "ok"


class FakeProvider:
    supports_streaming = True

    def __init__(self):
        self.chat_calls = 0
        self.stream_calls = 0

    async def chat(self, **_kwargs):
        self.chat_calls += 1
        return LLMResponse(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_data", "arguments": "{}"},
                }
            ],
            finish_reason=FinishReason.TOOL_CALLS,
        )

    async def stream_chat(self, *_args, **_kwargs):
        self.stream_calls += 1
        yield "text"


@pytest.mark.asyncio
async def test_planner_preserves_tool_calls_when_stream_callback_exists():
    registry = SkillRegistry(namespace="test")
    registry.register(
        Skill.executable(
            name="read_data",
            description="read",
            handler=_handler,
            risk_level=RiskLevel.READ,
        )
    )
    provider = FakeProvider()
    config = AgentConfig(
        llm_api_key="test",
        llm_max_retries=0,
    )
    planner = Agent._build_planner(registry, provider, config)

    result = await planner(
        [{"role": "user", "content": "read"}],
        1,
        stream_callback=lambda _token: None,
    )

    assert provider.chat_calls == 1
    assert provider.stream_calls == 0
    assert result["tool_calls"][0]["function"]["name"] == "read_data"
