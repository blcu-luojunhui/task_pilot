"""
Logging subscriber for harness events.

The harness emits structured lifecycle events; this component decides how to
turn those events into concise logs without making the harness own formatting.

支持两种模式：
- 默认模式：结构化单行日志（适合生产环境）
- verbose 模式：详细可读日志（适合开发调试）
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("agent.loop")

# 确保 logger 有 handler
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-5s | %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)


def _format_tool_calls(tool_calls) -> str:
    """格式化 tool_calls 为可读字符串"""
    lines = []
    for tc in tool_calls:
        func = tc.get("function", tc)
        name = func.get("name", tc.get("name", "?"))
        args = func.get("arguments", tc.get("arguments", ""))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                pass
        args_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)
        if len(args_str) > 120:
            args_str = args_str[:120] + "..."
        lines.append(f"{name}({args_str})")
    return " | ".join(lines)


@dataclass
class HarnessEventLogger:
    """
    Harness 事件日志器

    verbose=False: 结构化单行日志（生产环境）
    verbose=True:  详细可读日志（开发调试）
    """

    verbose: bool = False

    warning_events: frozenset = frozenset(
        {
            "budget_exhausted",
            "constraint_violation",
            "max_steps_reached",
            "run_cancelled",
        }
    )

    def log(self, event: Any) -> None:
        if self.verbose:
            self._log_verbose(event)
        else:
            self._log_compact(event)

    # ==================== Verbose 模式 ====================
    @staticmethod
    def _log_verbose(event: Any) -> None:
        """详细可读日志"""
        state = event.state
        name = event.name
        payload = event.payload
        trace = state.trace_id

        if name == "run_start":
            logger.info(
                "[%s] ── Agent Loop START ── goal=%r  budget=%d steps",
                trace,
                state.goal,
                state.max_steps,
            )

        elif name == "step_start":
            logger.info("[%s] ── Step %d/%d ──", trace, state.step, state.max_steps)

        elif name == "think_start":
            logger.debug("[%s] Think  | calling LLM...", trace)

        elif name == "think_end":
            msg = payload.get("assistant_message")
            if msg:
                content = msg.get("content", "")
                tool_calls = msg.get("tool_calls")

                if tool_calls:
                    logger.info(
                        "[%s] Think  | tool_call → %s",
                        trace,
                        _format_tool_calls(tool_calls),
                    )
                    if content:
                        short = content[:80] + "..." if len(content) > 80 else content
                        logger.debug("[%s] Think  | note: %s", trace, short)
                elif content:
                    logger.info("[%s] Think  | final_answer (%d chars)", trace, len(content))
                    display = content[:200] + "..." if len(content) > 200 else content
                    for line in display.split("\n")[:8]:
                        logger.debug("[%s]          %s", trace, line)
            else:
                logger.warning("[%s] Think  | no response from LLM", trace)

        elif name == "act_start":
            tool_calls = payload.get("tool_calls", [])
            names = [tc.get("name", "?") for tc in tool_calls]
            logger.info(
                "[%s] Act    | executing %d tool(s): %s",
                trace,
                len(tool_calls),
                ", ".join(names),
            )

        elif name == "act_end":
            results = payload.get("tool_results", [])
            for r in results:
                content = r.get("content", "")
                is_error = str(content).startswith("Error:")
                display = content[:150] + "..." if len(content) > 150 else content
                if is_error:
                    logger.error("[%s] Act    | FAILED: %s", trace, display)
                else:
                    logger.info("[%s] Act    | OK: %s", trace, display)

        elif name == "feedback_collected":
            messages = payload.get("messages", [])
            if messages:
                logger.info("[%s] Feedback | injected %d message(s)", trace, len(messages))

        elif name == "step_end":
            logger.info(
                "[%s] Observe | step=%d  tool_calls=%d  consecutive_errors=%d",
                trace,
                state.step,
                len(state.tool_calls),
                state.consecutive_tool_errors,
            )

        elif name == "run_end":
            result = payload.get("result")
            if result:
                status = "SUCCESS" if result.success else "FAILED"
                logger.info(
                    "[%s] ── Agent Loop END ── status=%s  steps=%d  tools=%d  duration=%.2fs  reason=%s",
                    trace,
                    status,
                    result.total_steps,
                    result.tool_calls_count,
                    result.duration_seconds,
                    result.stop_reason.value if result.stop_reason else "N/A",
                )

        elif name == "run_error":
            logger.error("[%s] ERROR  | %s", trace, payload.get("error"))

    # ==================== Compact 模式 ====================

    def _log_compact(self, event: Any) -> None:
        """结构化单行日志（生产环境）"""
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

        if "assistant_message" in payload:
            summary["assistant_message"] = self._summarize_message(payload["assistant_message"])
        if "tool_calls" in payload:
            summary["tool_calls"] = [
                {"id": call.get("id"), "name": call.get("name")} for call in payload["tool_calls"]
            ]
        if "tool_results" in payload:
            summary["tool_results"] = [
                {
                    "tool_call_id": r.get("tool_call_id"),
                    "is_error": str(r.get("content", "")).startswith("Error:"),
                }
                for r in payload["tool_results"]
            ]
        if "result" in payload:
            result = payload["result"]
            summary["result"] = {
                "success": result.success,
                "stop_reason": result.stop_reason.value if result.stop_reason else None,
                "steps": result.total_steps,
                "duration": round(result.duration_seconds, 3),
            }

        return summary

    @staticmethod
    def _summarize_message(message: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if message is None:
            return None
        content = message.get("content")
        if isinstance(content, str) and len(content) > 120:
            content = f"{content[:117]}..."
        return {
            "role": message.get("role"),
            "content": content,
            "has_tool_calls": bool(message.get("tool_calls")),
        }


__all__ = ["HarnessEventLogger"]
