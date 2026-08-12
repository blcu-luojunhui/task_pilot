"""Human approval policy for side-effecting tool calls."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.core.agents.capabilities.skills import RiskLevel, SkillRegistry
from src.core.agents.state.protocol import ToolCall
from src.core.agents.capabilities.skills.security import redact_sensitive_data


class ApprovalPolicyError(ValueError):
    """Raised when an untrusted approval policy is invalid."""


@dataclass(frozen=True)
class ApprovalRequest:
    """Immutable request created before any gated tool call executes."""

    request_id: str
    trace_id: str
    step: int
    tool_calls: tuple[dict[str, Any], ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "step": self.step,
            "tool_calls": [dict(call) for call in self.tool_calls],
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ApprovalDecision:
    """Decision supplied by a trusted caller when resuming a run."""

    request_id: str
    decision: str
    reason: Optional[str] = None
    actor_id: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> Optional["ApprovalDecision"]:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ApprovalPolicyError("approval_decision must be an object")
        request_id = raw.get("request_id")
        decision = raw.get("decision")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ApprovalPolicyError("approval_decision.request_id is required")
        if decision not in {"approve", "reject"}:
            raise ApprovalPolicyError("approval_decision.decision must be approve or reject")
        reason = raw.get("reason")
        actor_id = raw.get("actor_id")
        if reason is not None and not isinstance(reason, str):
            raise ApprovalPolicyError("approval_decision.reason must be a string")
        if actor_id is not None and not isinstance(actor_id, str):
            raise ApprovalPolicyError("approval_decision.actor_id must be a string")
        return cls(request_id.strip(), decision, reason, actor_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision,
            "reason": (
                str(redact_sensitive_data(self.reason))
                if self.reason is not None
                else None
            ),
            "actor_id": self.actor_id,
        }


@dataclass(frozen=True)
class ApprovalPolicy:
    """Per-run policy deciding which advertised tools need human approval."""

    required_risk_levels: frozenset[RiskLevel] = field(
        default_factory=lambda: frozenset({RiskLevel.WRITE, RiskLevel.DESTRUCTIVE})
    )
    required_tools: frozenset[str] = field(default_factory=frozenset)
    exempt_tools: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "ApprovalPolicy":
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise ApprovalPolicyError("approval_policy must be an object")

        levels = raw.get("required_risk_levels", ["write", "destructive"])
        if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
            raise ApprovalPolicyError("required_risk_levels must be a list of strings")
        try:
            required_levels = frozenset(RiskLevel(level) for level in levels)
        except (TypeError, ValueError) as exc:
            raise ApprovalPolicyError(
                "required_risk_levels must contain only read, write, or destructive"
            ) from exc

        required_tools = cls._parse_names(raw.get("required_tools", []), "required_tools")
        exempt_tools = cls._parse_names(raw.get("exempt_tools", []), "exempt_tools")
        overlap = required_tools & exempt_tools
        if overlap:
            raise ApprovalPolicyError(
                "tools cannot be both required and exempt: " + ", ".join(sorted(overlap))
            )
        return cls(required_levels, required_tools, exempt_tools)

    @staticmethod
    def _parse_names(value: Any, field_name: str) -> frozenset[str]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ApprovalPolicyError(f"{field_name} must be a list of strings")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ApprovalPolicyError(f"{field_name} must contain non-empty strings")
        return frozenset(item.strip() for item in value)

    def requires_approval(self, tool_name: str, risk_level: RiskLevel) -> bool:
        if tool_name in self.exempt_tools:
            return False
        return tool_name in self.required_tools or risk_level in self.required_risk_levels

    def create_request(
        self,
        tool_calls: Iterable[ToolCall],
        registry: SkillRegistry,
        *,
        trace_id: str,
        step: int,
    ) -> Optional[ApprovalRequest]:
        pending_calls = []
        has_gated_call = False
        for call in tool_calls:
            skill = registry.get(call.name)
            risk_level = skill.risk_level if skill is not None else RiskLevel.DESTRUCTIVE
            requires_approval = self.requires_approval(call.name, risk_level)
            has_gated_call = has_gated_call or requires_approval
            pending_calls.append(
                {
                    "call_id": call.id,
                    "tool_name": call.name,
                    "arguments": redact_sensitive_data(call.arguments),
                    "risk_level": risk_level.value,
                    "requires_approval": requires_approval,
                }
            )
        if not has_gated_call:
            return None
        return ApprovalRequest(
            request_id=f"apr-{uuid.uuid4().hex}",
            trace_id=trace_id,
            step=step,
            tool_calls=tuple(pending_calls),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_risk_levels": sorted(level.value for level in self.required_risk_levels),
            "required_tools": sorted(self.required_tools),
            "exempt_tools": sorted(self.exempt_tools),
        }


__all__ = [
    "ApprovalDecision",
    "ApprovalPolicy",
    "ApprovalPolicyError",
    "ApprovalRequest",
]
