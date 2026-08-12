import pytest

from src.core.agents.capabilities.skills import RiskLevel, Skill, ToolPolicy, ToolPolicyError
from src.core.agents.runtime.harness import ApprovalPolicy
from src.core.agents.state.protocol import ToolCall


async def _handler(_ctx):
    return "ok"


def _skill(name: str, risk: RiskLevel) -> Skill:
    return Skill.executable(
        name=name,
        description=name,
        handler=_handler,
        risk_level=risk,
    )


def test_default_policy_is_read_only():
    policy = ToolPolicy.from_mapping(None)

    assert policy.permits(_skill("read_data", RiskLevel.READ))
    assert not policy.permits(_skill("write_data", RiskLevel.WRITE))
    assert not policy.permits(_skill("delete_data", RiskLevel.DESTRUCTIVE))


def test_policy_can_explicitly_enable_write_and_filter_names():
    policy = ToolPolicy.from_mapping(
        {
            "allowed_risk_levels": ["read", "write"],
            "allowed_tools": ["read_data", "write_data"],
            "blocked_tools": ["blocked_read"],
        }
    )
    skills = [
        _skill("read_data", RiskLevel.READ),
        _skill("write_data", RiskLevel.WRITE),
        _skill("blocked_read", RiskLevel.READ),
        _skill("delete_data", RiskLevel.DESTRUCTIVE),
    ]

    assert [skill.name for skill in policy.filter_skills(skills)] == [
        "read_data",
        "write_data",
    ]


def test_guard_only_allows_tools_advertised_to_model():
    policy = ToolPolicy.from_mapping({"allowed_risk_levels": ["read"]})
    advertised = [_skill("visible", RiskLevel.READ)]
    guard = policy.to_guard(advertised)

    assert guard.check(advertised[0]) is None
    assert "not in the allowed tools list" in guard.check(_skill("hidden", RiskLevel.READ))


def test_approval_request_discloses_entire_frozen_tool_batch():
    skills = {
        "read_data": _skill("read_data", RiskLevel.READ),
        "write_data": _skill("write_data", RiskLevel.WRITE),
    }
    registry = type(
        "Registry",
        (),
        {"get": lambda _self, name: skills.get(name)},
    )()
    request = ApprovalPolicy().create_request(
        [
            ToolCall("call-read", "read_data", {"id": 1}),
            ToolCall("call-write", "write_data", {"id": 1}),
        ],
        registry,
        trace_id="trace-batch",
        step=1,
    )

    assert request is not None
    assert [call["tool_name"] for call in request.tool_calls] == ["read_data", "write_data"]
    assert [call["requires_approval"] for call in request.tool_calls] == [False, True]


@pytest.mark.parametrize(
    "raw",
    [
        {"allowed_risk_levels": []},
        {"allowed_risk_levels": ["admin"]},
        {"allowed_tools": "read_data"},
        {"allowed_tools": ["read_data"], "blocked_tools": ["read_data"]},
    ],
)
def test_invalid_policy_is_rejected(raw):
    with pytest.raises(ToolPolicyError):
        ToolPolicy.from_mapping(raw)
