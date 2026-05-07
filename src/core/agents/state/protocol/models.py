"""Protocol models for agent messages"""

import json
from typing import Any, Dict, Union
from dataclasses import dataclass


@dataclass
class ToolCall:
    """
    标准化的工具调用表示

    无论 LLM 返回什么格式，最终都转换为这个统一结构。
    """

    id: str
    name: str
    arguments: Dict[str, Any]  # 已解析的参数字典

    def to_dict(self) -> Dict[str, Any]:
        """转换为 OpenAI 兼容的 dict 格式"""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }

    @classmethod
    def from_openai_format(cls, raw: Dict[str, Any]) -> "ToolCall":
        """
        从 OpenAI/DeepSeek 格式解析

        格式: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
        """
        func = raw.get("function", {})
        arguments = func.get("arguments", "{}")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        return cls(
            id=raw.get("id", ""),
            name=func.get("name", ""),
            arguments=arguments if isinstance(arguments, dict) else {},
        )

    @classmethod
    def from_claude_format(cls, raw: Dict[str, Any]) -> "ToolCall":
        """
        从 Claude 格式解析

        格式: {"id": "...", "type": "tool_use", "name": "...", "input": {...}}
        """
        arguments = raw.get("input", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        return cls(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            arguments=arguments if isinstance(arguments, dict) else {},
        )

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ToolCall":
        """
        自动检测格式并解析

        支持：
        - OpenAI/DeepSeek: {"type": "function", "function": {...}}
        - Claude: {"type": "tool_use", "name": "...", "input": {...}}
        - 已标准化: {"id": "...", "name": "...", "arguments": {...}}
        """
        raw_type = raw.get("type", "")

        if raw_type == "function" or "function" in raw:
            return cls.from_openai_format(raw)
        elif raw_type == "tool_use" or "input" in raw:
            return cls.from_claude_format(raw)
        elif "name" in raw and "arguments" in raw:
            # 已经是标准格式
            arguments = raw.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
            return cls(
                id=raw.get("id", ""),
                name=raw["name"],
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        else:
            # 兜底
            return cls(id=raw.get("id", ""), name=raw.get("name", ""), arguments={})
