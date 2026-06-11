from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple

from src.core.agents.capabilities.skills.model import Skill


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """解析 YAML frontmatter，返回 (metadata, body)。"""
    text = content.strip()
    if not text.startswith("---"):
        return {}, content

    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, content

    metadata: Dict[str, str] = {}
    end = len(lines)
    for i in range(1, len(lines)):
        line = lines[i].strip()
        if line == "---":
            end = i
            break
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    body = "\n".join(lines[end + 1 :]).strip()
    return metadata, body


def build_personal_skill_markdown(
    *,
    name: str,
    description: str,
    category: str,
    body: str,
    scope: str = "agent:*",
) -> str:
    desc = description.replace("\n", " ").strip()
    header = "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {desc}",
            f"category: {category}",
            "skill_type: knowledge",
            f"scope: {scope}",
            "---",
            "",
        ]
    )
    return f"{header}{body.strip()}\n"


def skill_to_markdown(skill: Skill) -> str:
    """将注册表中的 Skill 序列化为 Markdown 文件内容。"""
    category = skill.domain or "general"
    risk = skill.risk_level.value if skill.risk_level else "read"
    description = _first_line(skill.description or skill.name)

    header_lines = [
        "---",
        f"name: {skill.name}",
        f"description: {description}",
        f"category: {category}",
        f"skill_type: {skill.skill_type.value}",
        f"scope: {skill.scope}",
    ]
    if skill.is_executable:
        header_lines.append(f"risk_level: {risk}")
    if skill.tags:
        header_lines.append(f"tags: {', '.join(skill.tags)}")
    header_lines.append("---")
    header_lines.append("")

    body_lines: list[str] = []

    if skill.description:
        body_lines.extend(["## Description", "", skill.description.strip(), ""])

    if skill.is_knowledge and skill.content:
        body_lines.extend([skill.content.strip(), ""])

    if skill.guidelines:
        body_lines.extend(["## Guidelines", ""])
        body_lines.extend(f"- {item}" for item in skill.guidelines)
        body_lines.append("")

    if skill.is_executable and skill.parameters:
        body_lines.extend(["## Parameters", "", "```json"])
        body_lines.append(json.dumps(skill.parameters, indent=4, ensure_ascii=False))
        body_lines.extend(["```", ""])

    if skill.is_executable and skill.dependencies:
        body_lines.extend(["## Dependencies", ""])
        body_lines.extend(f"- {dep}" for dep in skill.dependencies)
        body_lines.append("")

    if skill.is_executable and skill.examples:
        body_lines.extend(["## Examples", "", "```json"])
        body_lines.append(json.dumps(skill.examples, indent=4, ensure_ascii=False))
        body_lines.extend(["```", ""])

    return "\n".join(header_lines + body_lines).strip() + "\n"


def extract_personal_fields(content: str) -> Dict[str, Any]:
    """从 Markdown 内容提取个人 skill 元数据。"""
    metadata, body = parse_frontmatter(content)
    name = metadata.get("name", "").strip()
    if not name:
        match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        name = match.group(1).strip() if match else "untitled-skill"

    description = metadata.get("description", "").strip()
    if not description:
        section = _extract_markdown_section(body, "Description")
        description = _first_line(section or body)

    category = metadata.get("category", "general").strip() or "general"
    scope = metadata.get("scope", "agent:*").strip() or "agent:*"

    return {
        "name": name,
        "description": description[:512],
        "category": category[:64],
        "scope": scope[:64],
        "body": body,
    }


def _extract_markdown_section(body: str, section_name: str) -> str:
    lines = body.splitlines()
    in_section = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and section_name.lower() in stripped.lower():
            in_section = True
            continue
        if in_section and stripped.startswith("##"):
            break
        if in_section:
            collected.append(line)
    return "\n".join(collected).strip()


def default_personal_skill_template(name: str, category: str = "chat_ops") -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower() or "new-skill"
    body = "\n".join(
        [
            "## Description",
            "",
            "在此描述 skill 的用途与触发场景。",
            "",
            "## Guidelines",
            "",
            "",
        ]
    )
    return build_personal_skill_markdown(
        name=slug,
        description="在此填写简短描述",
        category=category,
        body=body,
    )


__all__ = [
    "build_personal_skill_markdown",
    "default_personal_skill_template",
    "extract_personal_fields",
    "parse_frontmatter",
    "skill_to_markdown",
]
