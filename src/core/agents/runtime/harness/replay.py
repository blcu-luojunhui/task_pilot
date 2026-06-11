"""确定性回放组件 (OPT-12) — 基于录制的事件/响应重放执行过程"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReplayRecord:
    """单步录制"""

    step: int
    assistant_message: Dict[str, Any]
    tool_results: List[Dict[str, Any]]
    state_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class ReplaySession:
    """完整录制会话"""

    trace_id: str
    goal: str
    steps: List[ReplayRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ReplayRecorder:
    """录制器：hook step_end 事件，把每步数据落盘"""

    def __init__(self, storage_dir: Path | str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def record_step(
        self,
        session: ReplaySession,
        step: int,
        assistant_message: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        session.steps.append(
            ReplayRecord(
                step=step,
                assistant_message=assistant_message,
                tool_results=tool_results,
                state_snapshot=state_snapshot,
            )
        )

    def save(self, session: ReplaySession) -> Path:
        path = self.storage_dir / f"{session.trace_id}.json"
        data = {
            "trace_id": session.trace_id,
            "goal": session.goal,
            "metadata": session.metadata,
            "steps": [
                {
                    "step": r.step,
                    "assistant_message": r.assistant_message,
                    "tool_results": r.tool_results,
                    "state_snapshot": r.state_snapshot,
                }
                for r in session.steps
            ],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Replay session saved: %s (%d steps)", path, len(session.steps))
        return path

    def load(self, trace_id: str) -> ReplaySession:
        path = self.storage_dir / f"{trace_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Replay session not found: {trace_id}")
        data = json.loads(path.read_text())
        session = ReplaySession(
            trace_id=data["trace_id"],
            goal=data["goal"],
            metadata=data.get("metadata", {}),
        )
        for s in data["steps"]:
            session.steps.append(
                ReplayRecord(
                    step=s["step"],
                    assistant_message=s["assistant_message"],
                    tool_results=s["tool_results"],
                    state_snapshot=s.get("state_snapshot"),
                )
            )
        return session


class ReplayProvider:
    """回放用 Planner：按录制顺序吐出 assistant_message"""

    def __init__(self, records: List[ReplayRecord]):
        self._records = records
        self._cursor = -1

    async def __call__(self, messages: list, step: int, **kwargs) -> Dict[str, Any]:
        self._cursor += 1
        if self._cursor >= len(self._records):
            return {"role": "assistant", "content": ""}
        return dict(self._records[self._cursor].assistant_message)


class ReplayActor:
    """回放用 Actor：按录制返回 tool_results"""

    def __init__(self, records: List[ReplayRecord]):
        self._records = records
        self._cursor = -1

    async def run(self, state: Any, tool_calls: list) -> List[Dict[str, Any]]:
        self._cursor += 1
        if self._cursor >= len(self._records):
            return []
        return [dict(r) for r in self._records[self._cursor].tool_results]


__all__ = ["ReplayRecorder", "ReplayProvider", "ReplayActor", "ReplayRecord", "ReplaySession"]
