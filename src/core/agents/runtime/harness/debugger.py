"""
Debugger - 追踪和回放
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class TraceEvent:
    """追踪事件"""

    event_type: str
    timestamp: datetime
    data: Dict[str, Any]
    step_number: Optional[int] = None


class Debugger:
    """
    Agent 调试器

    功能：
    1. 记录执行追踪
    2. 回放执行过程
    3. 断点调试
    """

    def __init__(self):
        self.traces: List[TraceEvent] = []
        self.breakpoints: List[int] = []

    def record(self, event_type: str, data: Dict[str, Any], step: Optional[int] = None):
        """记录事件"""
        event = TraceEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            data=data,
            step_number=step,
        )
        self.traces.append(event)

    def save_trace(self, filepath: str):
        """保存追踪到文件"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "type": t.event_type,
                        "timestamp": t.timestamp.isoformat(),
                        "data": t.data,
                        "step": t.step_number,
                    }
                    for t in self.traces
                ],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def load_trace(self, filepath: str):
        """从文件加载追踪"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.traces = [
                TraceEvent(
                    event_type=t["type"],
                    timestamp=datetime.fromisoformat(t["timestamp"]),
                    data=t["data"],
                    step_number=t.get("step"),
                )
                for t in data
            ]

    async def replay(self, agent, start_step: int = 0, end_step: Optional[int] = None):
        """
        回放执行过程

        根据录制的 trace 事件重放 agent 执行，支持断点暂停。

        Args:
            agent: Agent 实例（用于重新执行）
            start_step: 起始步数
            end_step: 结束步数（None 表示到最后）

        Yields:
            Dict: 每个 step 的回放信息
        """
        if not self.traces:
            logger.warning("No traces loaded for replay")
            return

        # 按步数过滤事件
        steps: Dict[int, List[TraceEvent]] = {}
        for event in self.traces:
            if event.step_number is not None:
                step = event.step_number
                if step < start_step:
                    continue
                if end_step is not None and step > end_step:
                    continue
                if step not in steps:
                    steps[step] = []
                steps[step].append(event)

        for step_num in sorted(steps.keys()):
            # 检查断点
            if step_num in self.breakpoints:
                logger.info(f"Breakpoint hit at step {step_num}")
                yield {
                    "step": step_num,
                    "status": "breakpoint",
                    "events": [e.event_type for e in steps[step_num]],
                }
                continue

            step_events = steps[step_num]
            replay_info = {
                "step": step_num,
                "event_count": len(step_events),
                "event_types": [e.event_type for e in step_events],
            }

            # 提取关键信息
            for event in step_events:
                if event.event_type == "think_end":
                    msg = event.data.get("assistant_message", {})
                    replay_info["think_result"] = {
                        "content": (msg.get("content", "") or "")[:200],
                        "tool_calls": len(msg.get("tool_calls") or []),
                    }
                elif event.event_type == "act_end":
                    results = event.data.get("tool_results", [])
                    replay_info["tool_results"] = len(results)
                elif event.event_type == "step_end":
                    replay_info["completed"] = True
                elif event.event_type in ("run_error", "run_stopped", "run_end"):
                    replay_info["stop_event"] = event.event_type

            yield replay_info

    def set_breakpoint(self, step: int):
        """设置断点"""
        if step not in self.breakpoints:
            self.breakpoints.append(step)

    def clear_breakpoints(self):
        """清除所有断点"""
        self.breakpoints.clear()


__all__ = ["Debugger", "TraceEvent"]
