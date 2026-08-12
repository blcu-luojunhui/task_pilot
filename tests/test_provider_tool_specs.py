import pytest

from src.core.agent_task.run_goal import _build_planner
from src.core.agents.capabilities.llm.base import LLMConfig, LLMResponse
from src.core.agents.capabilities.skills import RiskLevel, Skill


async def _handler(_ctx, value: str):
    return value


class FakeProvider:
    supports_streaming = False

    def __init__(self, name):
        self.name = name
        self.config = LLMConfig(api_key="test", model="test")
        self.tools = None

    async def chat(self, **kwargs):
        self.tools = kwargs["tools"]
        return LLMResponse(content="done")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["openai", "claude"])
async def test_http_planner_serializes_provider_specific_tool_schema(provider_name):
    provider = FakeProvider(provider_name)
    tool = Skill.executable(
        name="echo",
        description="echo",
        handler=_handler,
        risk_level=RiskLevel.READ,
        parameters={"value": {"type": "string", "required": True}},
    )
    planner = _build_planner(provider, [tool])

    await planner([{"role": "user", "content": "echo"}], 1)

    if provider_name == "claude":
        assert provider.tools[0]["input_schema"]["type"] == "object"
        assert "function" not in provider.tools[0]
    else:
        assert provider.tools[0]["type"] == "function"
        assert provider.tools[0]["function"]["parameters"]["type"] == "object"
