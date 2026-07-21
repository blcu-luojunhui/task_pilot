"""
Skill Markdown 解析器 — 解析 SKILL.md YAML frontmatter。

注意：本地文件系统加载能力已移除，Skill 唯一来源为 MySQL skill_registry 表。
FrontmatterParser 供 Registry.load_from_db_rows() 解析 DB 中的 Markdown 内容。
"""

import logging
from typing import Dict, List, Optional

from .model import Skill

logger = logging.getLogger(__name__)


# ── 共享工具函数 ──────────────────────────────────────


def _filename_to_title(filename: str) -> str:
    return " ".join(word.capitalize() for word in filename.split("-"))


def _extract_section(lines: List[str], section_name: str) -> Optional[str]:
    in_section = False
    section_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and section_name.lower() in stripped.lower():
            in_section = True
            continue
        if in_section and stripped.startswith("##"):
            break
        if in_section:
            section_lines.append(line)
    return "\n".join(section_lines).strip() if section_lines else None


def _extract_list_items(lines: List[str], section_name: str) -> List[str]:
    section = _extract_section(lines, section_name)
    if not section:
        return []
    items = []
    for line in section.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:])
    return items


class FrontmatterParser:
    """YAML Frontmatter 格式解析器 — 供 Registry.load_from_db_rows() 使用。"""

    def can_parse(self, content: str) -> bool:
        return content.strip().startswith("---")

    def parse(self, content: str, filename: str) -> Optional[Skill]:
        lines = content.split("\n")

        if not lines[0].strip() == "---":
            return None

        # 提取 frontmatter
        frontmatter = {}
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            if line == "---":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip()
            i += 1

        name = frontmatter.get("name") or _filename_to_title(filename)
        description = frontmatter.get("description", "")
        domain = frontmatter.get("category", "general")
        scope = frontmatter.get("scope", "agent:*")
        parent_id = frontmatter.get("parent")

        remaining_content = "\n".join(lines[i + 1 :])
        remaining_lines = remaining_content.split("\n")

        when_to_use = _extract_list_items(remaining_lines, "When to use")
        if when_to_use:
            description += "\n\n适用场景：\n" + "\n".join(f"- {item}" for item in when_to_use)

        guidelines = _extract_list_items(remaining_lines, "Guidelines")
        content = remaining_content.strip()

        return Skill.knowledge(
            scope=scope,
            name=name,
            description=description.strip(),
            domain=domain,
            content=content,
            guidelines=guidelines,
            parent_id=parent_id,
        )


class InlineMetadataParser:
    """行内元数据格式解析器（备用）。"""

    def can_parse(self, content: str) -> bool:
        return not content.strip().startswith("---")

    def parse(self, content: str, filename: str) -> Optional[Skill]:
        lines = content.split("\n")

        name = self._extract_title(lines) or _filename_to_title(filename)
        metadata = self._extract_metadata(lines)
        domain = metadata.get("category", "general")
        scope = metadata.get("scope", "agent:*")
        parent_id = metadata.get("parent")

        description = _extract_section(lines, "Description") or ""
        guidelines = _extract_list_items(lines, "Guidelines")

        content_lines = []
        skip_metadata = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                continue
            if stripped.startswith(">"):
                skip_metadata = True
                continue
            if skip_metadata and not stripped:
                skip_metadata = False
                continue
            content_lines.append(line)

        content = "\n".join(content_lines).strip()

        return Skill.knowledge(
            scope=scope,
            name=name,
            description=description.strip(),
            domain=domain,
            content=content,
            guidelines=guidelines,
            parent_id=parent_id,
        )

    @staticmethod
    def _extract_title(lines: List[str]) -> Optional[str]:
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return None

    @staticmethod
    def _extract_metadata(lines: List[str]) -> Dict[str, str]:
        metadata = {}
        for line in lines:
            line = line.strip()
            if line.startswith(">"):
                content = line[1:].strip()
                if ":" in content:
                    key, value = content.split(":", 1)
                    metadata[key.strip()] = value.strip()
        return metadata


__all__ = ["FrontmatterParser", "InlineMetadataParser"]
