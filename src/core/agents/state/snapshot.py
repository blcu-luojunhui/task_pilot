"""
状态快照管理

支持保存和恢复 Agent 状态
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import asdict

from .models import AgentState, AgentLoopState, StopReason


class StateSnapshot:
    """状态快照管理器"""

    def __init__(self, storage_dir: Path, max_tool_result_length: int = 2000):
        """
        初始化快照管理器

        Args:
            storage_dir: 快照存储目录
            max_tool_result_length: tool_output 最大字符数，超出截断
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_tool_result_length = max_tool_result_length

    def _truncate(self, text: Optional[str]) -> Optional[str]:
        """截断过长文本"""
        if text is None:
            return None
        if len(text) > self.max_tool_result_length:
            return text[:self.max_tool_result_length] + "... [truncated]"
        return text

    def save(
        self,
        agent_id: str,
        loop_state: AgentLoopState,
        lifecycle_state: AgentState,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        保存状态快照

        Args:
            agent_id: Agent ID
            loop_state: 循环状态
            lifecycle_state: 生命周期状态
            metadata: 额外元数据

        Returns:
            快照 ID
        """
        snapshot_id = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_path = self.storage_dir / f"{snapshot_id}.json"

        snapshot_data = {
            "schema_version": 2,
            "snapshot_id": snapshot_id,
            "agent_id": agent_id,
            "lifecycle_state": lifecycle_state.value,
            "loop_state": {
                "goal": loop_state.goal,
                "trace_id": loop_state.trace_id,
                "step": loop_state.step,
                "max_steps": loop_state.max_steps,
                "messages": loop_state.messages,
                "metadata": loop_state.metadata,
                "tool_calls": [
                    {
                        "tool_name": tc.tool_name,
                        "tool_input": tc.tool_input,
                        "tool_output": self._truncate(tc.tool_output),
                        "error": tc.error,
                        "duration_ms": tc.duration_ms,
                    }
                    for tc in loop_state.tool_calls
                ],
                "steps": [
                    {
                        "step_number": s.step_number,
                        "thought": {
                            "type": s.thought.type.value if s.thought else None,
                            "content": s.thought.content if s.thought else "",
                        } if s.thought else None,
                        "action": {
                            "type": s.action.type.value if s.action else None,
                            "target": s.action.target if s.action else "",
                            "parameters": s.action.parameters if s.action else {},
                        } if s.action else None,
                        "observation": {
                            "result": s.observation.result if s.observation else None,
                            "success": s.observation.success if s.observation else False,
                            "error": s.observation.error if s.observation else None,
                            "duration_ms": s.observation.duration_ms if s.observation else 0.0,
                        } if s.observation else None,
                    }
                    for s in loop_state.steps
                ],
                "final_answer": loop_state.final_answer,
                "stop_reason": loop_state.stop_reason.value if loop_state.stop_reason else None,
                "consecutive_tool_errors": loop_state.consecutive_tool_errors,
            },
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }

        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)

        return snapshot_id

    def load(self, snapshot_id: str) -> tuple[AgentLoopState, AgentState, Dict[str, Any]]:
        """
        加载状态快照

        Args:
            snapshot_id: 快照 ID

        Returns:
            (循环状态, 生命周期状态, 元数据)

        Raises:
            FileNotFoundError: 如果快照不存在
        """
        snapshot_path = self.storage_dir / f"{snapshot_id}.json"

        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

        with open(snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 恢复 lifecycle state
        lifecycle_state = AgentState(data["lifecycle_state"])

        # 恢复 loop state
        loop_data = data["loop_state"]
        loop_state = AgentLoopState(
            goal=loop_data["goal"],
            max_steps=loop_data["max_steps"],
            trace_id=loop_data.get("trace_id", ""),
        )
        loop_state.step = loop_data["step"]
        loop_state.messages = loop_data["messages"]
        loop_state.final_answer = loop_data.get("final_answer")
        loop_state.consecutive_tool_errors = loop_data.get("consecutive_tool_errors", 0)
        loop_state.metadata = loop_data.get("metadata", {})

        if loop_data.get("stop_reason"):
            loop_state.stop_reason = StopReason(loop_data["stop_reason"])

        # 恢复 steps
        from ..engine.types import Thought, Action, Observation, Step, ThoughtType, ActionType

        for s_data in loop_data.get("steps", []):
            thought = None
            if s_data.get("thought"):
                t = s_data["thought"]
                thought_type = ThoughtType(t["type"]) if t.get("type") else ThoughtType.REASONING
                thought = Thought(type=thought_type, content=t.get("content", ""))
            action = None
            if s_data.get("action"):
                a = s_data["action"]
                action_type = ActionType(a["type"]) if a.get("type") else ActionType.TOOL_CALL
                action = Action(
                    type=action_type,
                    target=a.get("target", ""),
                    parameters=a.get("parameters", {}),
                )
            observation = None
            if s_data.get("observation"):
                o = s_data["observation"]
                observation = Observation(
                    action=action,
                    result=o.get("result"),
                    success=o.get("success", False),
                    error=o.get("error"),
                    duration_ms=o.get("duration_ms", 0.0),
                )
            loop_state.steps.append(
                Step(
                    step_number=s_data["step_number"],
                    thought=thought,
                    action=action,
                    observation=observation,
                )
            )

        # 恢复 tool_calls
        from .models import ToolCallRecord

        for tc_data in loop_data.get("tool_calls", []):
            loop_state.tool_calls.append(
                ToolCallRecord(
                    tool_name=tc_data.get("tool_name", tc_data.get("name", "")),
                    tool_input=tc_data.get("tool_input", tc_data.get("arguments", {})),
                    tool_output=tc_data.get("tool_output", tc_data.get("result")),
                    error=tc_data.get("error"),
                    duration_ms=tc_data.get("duration_ms", 0.0),
                )
            )

        metadata = data.get("metadata", {})

        return loop_state, lifecycle_state, metadata

    def list_snapshots(self, agent_id: Optional[str] = None) -> list[Dict[str, Any]]:
        """
        列出所有快照

        Args:
            agent_id: 可选的 Agent ID 过滤

        Returns:
            快照信息列表
        """
        snapshots = []

        for snapshot_file in self.storage_dir.glob("*.json"):
            try:
                with open(snapshot_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if agent_id and data.get("agent_id") != agent_id:
                    continue

                snapshots.append(
                    {
                        "snapshot_id": data["snapshot_id"],
                        "agent_id": data["agent_id"],
                        "lifecycle_state": data["lifecycle_state"],
                        "timestamp": data["timestamp"],
                        "goal": data["loop_state"]["goal"],
                        "step": data["loop_state"]["step"],
                    }
                )
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        # 按时间倒序排序
        snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
        return snapshots

    def delete(self, snapshot_id: str):
        """
        删除快照

        Args:
            snapshot_id: 快照 ID
        """
        snapshot_path = self.storage_dir / f"{snapshot_id}.json"
        if snapshot_path.exists():
            snapshot_path.unlink()


__all__ = ["StateSnapshot"]
