"""Human reconciliation protocol for ambiguous side-effecting tool calls."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.core.agents.capabilities.skills.security import (
    redact_sensitive_data,
    wrap_untrusted_tool_output,
)


class ReconciliationError(ValueError):
    """Raised when a reconciliation decision is malformed."""


@dataclass(frozen=True)
class ReconciliationDecision:
    """Trusted operator decision for one ambiguous tool execution."""

    tool_call_id: str
    decision: str
    result_content: Optional[str] = None
    reason: Optional[str] = None
    actor_id: Optional[str] = None

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]],
    ) -> Optional["ReconciliationDecision"]:
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise ReconciliationError("reconciliation_decision must be an object")
        tool_call_id = raw.get("tool_call_id")
        decision = raw.get("decision")
        result_content = raw.get("result_content")
        reason = raw.get("reason")
        actor_id = raw.get("actor_id")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            raise ReconciliationError("reconciliation_decision.tool_call_id is required")
        if decision not in {"completed", "failed"}:
            raise ReconciliationError(
                "reconciliation_decision.decision must be completed or failed"
            )
        if decision == "completed" and not isinstance(result_content, str):
            raise ReconciliationError(
                "reconciliation_decision.result_content must be a string for completed"
            )
        if result_content is not None and not isinstance(result_content, str):
            raise ReconciliationError("reconciliation_decision.result_content must be a string")
        if reason is not None and not isinstance(reason, str):
            raise ReconciliationError("reconciliation_decision.reason must be a string")
        if actor_id is not None and not isinstance(actor_id, str):
            raise ReconciliationError("reconciliation_decision.actor_id must be a string")
        return cls(tool_call_id.strip(), decision, result_content, reason, actor_id)

    def tool_message_content(self) -> str:
        if self.decision == "completed":
            safe_result = redact_sensitive_data(self.result_content or "")
            return wrap_untrusted_tool_output(str(safe_result))
        reason = redact_sensitive_data(
            self.reason or "downstream verification found no completed side effect"
        )
        return f"Error: Tool execution reconciled as failed by human reviewer: {reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "decision": self.decision,
            "result_content": self.result_content,
            "reason": (
                str(redact_sensitive_data(self.reason))
                if self.reason is not None
                else None
            ),
            "actor_id": self.actor_id,
        }

    def to_audit_dict(self) -> dict[str, Any]:
        result_digest = None
        if self.result_content is not None:
            result_digest = hashlib.sha256(self.result_content.encode("utf-8")).hexdigest()
        return {
            "tool_call_id": self.tool_call_id,
            "decision": self.decision,
            "reason": (
                str(redact_sensitive_data(self.reason))
                if self.reason is not None
                else None
            ),
            "actor_id": self.actor_id,
            "result_digest": result_digest,
        }


__all__ = [
    "ReconciliationDecision",
    "ReconciliationError",
]
