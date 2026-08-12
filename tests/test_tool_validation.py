import pytest

from src.core.agents.capabilities.skills import (
    ParameterValidator,
    RiskLevel,
    Skill,
    SkillValidationError,
)
from src.core.agents.capabilities.skills.serializer import OpenAIAdapter, ToolSpecSerializer


async def _handler(_ctx, **_params):
    return "ok"


def _nested_skill():
    return Skill.executable(
        name="plan",
        description="plan",
        handler=_handler,
        risk_level=RiskLevel.READ,
        parameters={
            "steps": {
                "type": "array",
                "required": True,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "done"]},
                    },
                    "required": ["title", "status"],
                    "additionalProperties": False,
                },
            },
            "limit": {"type": "integer", "required": False, "default": 10},
        },
    )


def test_serializer_preserves_nested_schema_contract():
    spec = ToolSpecSerializer(OpenAIAdapter()).serialize(_nested_skill())

    parameters = spec["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["steps"]["items"]["required"] == ["title", "status"]
    assert parameters["properties"]["limit"]["default"] == 10


def test_validator_accepts_nested_valid_payload():
    ParameterValidator.validate(
        _nested_skill(),
        {"steps": [{"title": "one", "status": "pending"}]},
    )


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"steps": [{"title": "one"}]}, r"steps\[0\]\.status"),
        ({"steps": [{"title": "one", "status": "invalid"}]}, "must be one of"),
        ({"steps": [{"title": "one", "status": "done", "extra": 1}]}, "Unknown"),
        ({"steps": [], "limit": True}, "expected type 'integer'"),
    ],
)
def test_validator_rejects_invalid_nested_payload(params, message):
    with pytest.raises(SkillValidationError, match=message):
        ParameterValidator.validate(_nested_skill(), params)
