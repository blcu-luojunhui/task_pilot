"""Per-run tool capability policies.

The model only receives tool definitions allowed by the policy. The executor
uses the same policy as a second check so a fabricated tool call cannot bypass
the advertised capability set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from .guard import PermissionGuard
from .model import RiskLevel, Skill


class ToolPolicyError(ValueError):
    """Raised when an untrusted tool policy is invalid."""


@dataclass(frozen=True)
class ToolPolicy:
    """Immutable capability policy applied to one agent run."""

    allowed_risk_levels: frozenset[RiskLevel] = field(
        default_factory=lambda: frozenset({RiskLevel.READ})
    )
    allowed_tools: Optional[frozenset[str]] = None
    blocked_tools: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]],
        *,
        default_risk_levels: Iterable[RiskLevel] = (RiskLevel.READ,),
    ) -> "ToolPolicy":
        if raw is None:
            return cls(allowed_risk_levels=frozenset(default_risk_levels))
        if not isinstance(raw, Mapping):
            raise ToolPolicyError("tool_policy must be an object")

        levels = raw.get("allowed_risk_levels")
        allowed_levels = (
            frozenset(default_risk_levels)
            if levels is None
            else cls._parse_risk_levels(levels)
        )
        allowed_tools = cls._parse_tool_names(raw.get("allowed_tools"), "allowed_tools")
        blocked_tools = cls._parse_tool_names(raw.get("blocked_tools", []), "blocked_tools") or frozenset()

        overlap = (allowed_tools or frozenset()) & blocked_tools
        if overlap:
            raise ToolPolicyError(
                "tools cannot be both allowed and blocked: " + ", ".join(sorted(overlap))
            )
        return cls(allowed_levels, allowed_tools, blocked_tools)

    @staticmethod
    def _parse_risk_levels(value: Any) -> frozenset[RiskLevel]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
            raise ToolPolicyError("allowed_risk_levels must be a non-empty list of strings")
        try:
            return frozenset(RiskLevel(item) for item in value)
        except (TypeError, ValueError) as exc:
            raise ToolPolicyError(
                "allowed_risk_levels must contain only read, write, or destructive"
            ) from exc

    @staticmethod
    def _parse_tool_names(value: Any, field_name: str) -> Optional[frozenset[str]]:
        if value is None:
            return None
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ToolPolicyError(f"{field_name} must be a list of strings")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ToolPolicyError(f"{field_name} must contain non-empty strings")
        return frozenset(item.strip() for item in value)

    def denial_reason(self, skill: Skill) -> Optional[str]:
        return self.to_guard().check(skill)

    def permits(self, skill: Skill) -> bool:
        return self.denial_reason(skill) is None

    def filter_skills(self, skills: Iterable[Skill]) -> list[Skill]:
        return [skill for skill in skills if self.permits(skill)]

    def to_guard(self, advertised_skills: Optional[Iterable[Skill]] = None) -> PermissionGuard:
        advertised_names = (
            {skill.name for skill in advertised_skills}
            if advertised_skills is not None
            else None
        )
        if advertised_names is not None:
            allowed_tools = advertised_names
            if self.allowed_tools is not None:
                allowed_tools &= set(self.allowed_tools)
        else:
            allowed_tools = set(self.allowed_tools) if self.allowed_tools is not None else None
        return PermissionGuard(
            allowed_levels=set(self.allowed_risk_levels),
            allowed_tools=allowed_tools,
            blocked_tools=set(self.blocked_tools),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_risk_levels": sorted(level.value for level in self.allowed_risk_levels),
            "allowed_tools": sorted(self.allowed_tools) if self.allowed_tools is not None else None,
            "blocked_tools": sorted(self.blocked_tools),
        }


__all__ = ["ToolPolicy", "ToolPolicyError"]
