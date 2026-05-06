"""
工具描述序列化适配器

支持不同 LLM 的 function calling 格式
"""

import json
from typing import Any, Dict, List

from .model import Skill
from .types import ToolSpecAdapter


def _build_description_with_examples(skill: Skill) -> str:
    """构建包含 examples 的 description 文本"""
    description = skill.description
    if not skill.examples:
        return description

    parts = [description, "\n\nExamples:"]
    for ex in skill.examples:
        input_str = json.dumps(ex.get("input", {}), ensure_ascii=False)
        output_str = ex.get("output", "")
        parts.append(f"  Input: {input_str}")
        parts.append(f"  Output: {output_str}")
    return "\n".join(parts)


class OpenAIAdapter:
    """OpenAI function calling 格式适配器"""

    def to_spec(self, skill: Skill) -> Dict[str, Any]:
        """
        转换为 OpenAI function calling 格式
        """
        properties = {}
        required = []

        for param_name, param_spec in skill.parameters.items():
            prop = {
                "type": param_spec.get("type", "string"),
                "description": param_spec.get("description", ""),
            }

            if "default" in param_spec:
                prop["default"] = param_spec["default"]

            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]

            properties[param_name] = prop

            # 判断必填
            is_required = param_spec.get("required", "default" not in param_spec)
            if is_required:
                required.append(param_name)

        return {
            "name": skill.name,
            "description": _build_description_with_examples(skill),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


class ClaudeAdapter:
    """Anthropic Claude tool use 格式适配器"""

    def to_spec(self, skill: Skill) -> Dict[str, Any]:
        """
        转换为 Claude tool use 格式
        """
        properties = {}
        required = []

        for param_name, param_spec in skill.parameters.items():
            prop = {
                "type": param_spec.get("type", "string"),
                "description": param_spec.get("description", ""),
            }

            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]

            properties[param_name] = prop

            is_required = param_spec.get("required", "default" not in param_spec)
            if is_required:
                required.append(param_name)

        return {
            "name": skill.name,
            "description": _build_description_with_examples(skill),
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


class ToolSpecSerializer:
    """工具描述序列化器"""

    def __init__(self, adapter: ToolSpecAdapter = None):
        self.adapter = adapter or OpenAIAdapter()

    def serialize(self, skill: Skill) -> Dict[str, Any]:
        """序列化单个 Skill"""
        return self.adapter.to_spec(skill)

    def serialize_many(self, skills: List[Skill]) -> List[Dict[str, Any]]:
        """批量序列化"""
        return [self.serialize(skill) for skill in skills]

    def to_prompt(self, skills: List[Skill]) -> str:
        """生成文本格式的工具描述（供 prompt 注入）"""
        if not skills:
            return "No tools available."

        lines = ["Available Tools:"]
        for skill in skills:
            lines.append(f"\n### {skill.name}")
            lines.append(skill.description)

            if skill.parameters:
                lines.append("\nParameters:")
                for param_name, param_spec in skill.parameters.items():
                    param_type = param_spec.get("type", "string")
                    param_desc = param_spec.get("description", "")
                    is_required = param_spec.get("required", "default" not in param_spec)
                    req_marker = " (required)" if is_required else " (optional)"
                    lines.append(f"  - {param_name} ({param_type}){req_marker}: {param_desc}")

        return "\n".join(lines)


__all__ = ["OpenAIAdapter", "ClaudeAdapter", "ToolSpecSerializer"]
