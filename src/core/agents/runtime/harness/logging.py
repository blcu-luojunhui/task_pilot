"""
Logging subscriber for harness events.

The harness emits structured lifecycle events; this component decides how to
turn those events into concise logs without making the harness own formatting.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("src.core.agents.runtime.harness")


@dataclass
class HarnessEventLogger:
    """Log harness events in a concise, transcript-friendly shape."""

    warning_events: frozenset[str] = frozenset(
        {
            "budget_exhausted",
            "constraint_violation",
            "max_steps_reached",
            "run_cancelled",
        }
    )

    def log(self, event: Any) -> None:
        detail = self._summarize_payload(event.payload)
        log_method = logger.warning if event.name in self.warning_events else logger.info
        log_method(
            "agent_loop trace_id=%s event=%s step=%s stop_reason=%s detail=%s",
            event.trace_id,
            event.name,
            event.state.step,
            event.state.stop_reason.value if event.state.stop_reason else None,
            detail,
        )

    def _summarize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}

        if "metadata" in payload:
            summary["metadata"] = payload["metadata"]
        if "assistant_message" in payload:
            summary["assistant_message"] = self._summarize_message(
                payload["assistant_message"]
            )
        if "tool_calls" in payload:
            summary["tool_calls"] = [
                {
                    "id": call.get("id"),
                    "name": call.get("name"),
                }
                for call in payload["tool_calls"]
            ]
        if "tool_results" in payload:
            summary["tool_results"] = [
                {
                    "tool_call_id": result.get("tool_call_id"),
                    "name": result.get("name"),
                    "is_error": result.get("is_error"),
                }
                for result in payload["tool_results"]
            ]
        if "messages" in payload:
            summary["feedback_count"] = len(payload["messages"])
        if "result" in payload:
            result = payload["result"]
            summary["result"] = {
                "trace_id": result.trace_id,
                "success": result.success,
                "stop_reason": result.stop_reason.value,
                "total_steps": result.total_steps,
                "tool_calls_count": result.tool_calls_count,
                "duration_seconds": round(result.duration_seconds, 3),
            }
        if "record" in payload:
            record = payload["record"]
            summary["improvement_record"] = {
                "success": record.success,
                "stop_reason": record.stop_reason,
                "total_steps": record.total_steps,
                "tool_calls_count": record.tool_calls_count,
            }

        for key, value in payload.items():
            if key not in {
                "metadata",
                "assistant_message",
                "tool_calls",
                "tool_results",
                "messages",
                "result",
                "record",
            }:
                summary[key] = value

        return summary

    def _summarize_message(
        self,
        message: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if message is None:
            return None

        content = message.get("content")
        if isinstance(content, str) and len(content) > 120:
            content = f"{content[:117]}..."

        return {
            "role": message.get("role"),
            "content": content,
            "tool_calls": [
                {
                    "id": call.get("id"),
                    "name": call.get("name"),
                }
                for call in (message.get("tool_calls") or [])
            ],
        }


__all__ = ["HarnessEventLogger"]
