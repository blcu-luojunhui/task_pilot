"""
Skill Loader - 从 Markdown 文件加载 Skills

支持插件式解析器
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .model import Skill
from .types import MarkdownParser

logger = logging.getLogger(__name__)


class FrontmatterParser:
    """YAML Frontmatter 格式解析器"""

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

        name = frontmatter.get("name") or self._filename_to_title(filename)
        description = frontmatter.get("description", "")
        domain = frontmatter.get("category", "general")
        scope = frontmatter.get("scope", "agent:*")
        parent_id = frontmatter.get("parent")

        remaining_content = "\n".join(lines[i + 1:])
        remaining_lines = remaining_content.split("\n")

        when_to_use = self._extract_list_items(remaining_lines, "When to use")
        if when_to_use:
            description += "\n\n适用场景：\n" + "\n".join(f"- {item}" for item in when_to_use)

        guidelines = self._extract_list_items(remaining_lines, "Guidelines")
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

    @staticmethod
    def _filename_to_title(filename: str) -> str:
        return " ".join(word.capitalize() for word in filename.split("-"))

    @staticmethod
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

    def _extract_list_items(self, lines: List[str], section_name: str) -> List[str]:
        section_content = self._extract_section(lines, section_name)
        if not section_content:
            return []

        items = []
        for line in section_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
        return items


class InlineMetadataParser:
    """行内元数据格式解析器"""

    def can_parse(self, content: str) -> bool:
        return not content.strip().startswith("---")

    def parse(self, content: str, filename: str) -> Optional[Skill]:
        lines = content.split("\n")

        name = self._extract_title(lines) or self._filename_to_title(filename)
        metadata = self._extract_metadata(lines)
        domain = metadata.get("category", "general")
        scope = metadata.get("scope", "agent:*")
        parent_id = metadata.get("parent")

        description = self._extract_section(lines, "Description") or ""
        guidelines = self._extract_list_items(lines, "Guidelines")

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
    def _filename_to_title(filename: str) -> str:
        return " ".join(word.capitalize() for word in filename.split("-"))

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

    @staticmethod
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

    def _extract_list_items(self, lines: List[str], section_name: str) -> List[str]:
        section_content = self._extract_section(lines, section_name)
        if not section_content:
            return []

        items = []
        for line in section_content.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
        return items


class SkillLoader:
    """从 Markdown 文件加载 Skills，支持插件式解析器"""

    def __init__(self, skills_dir: str, parsers: Optional[List[MarkdownParser]] = None):
        self.skills_dir = Path(skills_dir)
        self.parsers: List[MarkdownParser] = parsers or [
            FrontmatterParser(),
            InlineMetadataParser(),
        ]

        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {skills_dir}")

    def load_all(self) -> List[Skill]:
        if not self.skills_dir.exists():
            return []

        skills = []
        for md_file in self.skills_dir.glob("*.md"):
            try:
                skill = self.load_file(md_file)
                if skill:
                    skills.append(skill)
                    logger.info(f"成功加载 skill: {skill.name} from {md_file.name}")
            except Exception as e:
                logger.error(f"加载 skill 失败 {md_file}: {e}", exc_info=True)

        return skills

    def load_file(self, file_path: Path) -> Optional[Skill]:
        if not file_path.exists():
            logger.warning(f"文件不存在: {file_path}")
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self.parse_markdown(content, file_path.stem)

    def parse_markdown(self, content: str, filename: str) -> Optional[Skill]:
        """使用注册的解析器链解析 Markdown"""
        for parser in self.parsers:
            if parser.can_parse(content):
                return parser.parse(content, filename)
        return None



def load_skills_from_dir(skills_dir: Optional[str] = None) -> List[Skill]:
    """从目录加载所有 Skills"""
    all_skills = []

    # 加载内置 skills
    builtin_skills_dir = Path(__file__).parent.parent.parent.parent.parent / "skills"
    if builtin_skills_dir.exists():
        loader = SkillLoader(str(builtin_skills_dir))
        builtin_skills = loader.load_all()
        all_skills.extend(builtin_skills)
        logger.info(f"加载了 {len(builtin_skills)} 个内置 skills")

    # 加载用户自定义 skills
    if skills_dir:
        loader = SkillLoader(skills_dir)
        custom_skills = loader.load_all()
        all_skills.extend(custom_skills)
        logger.info(f"加载了 {len(custom_skills)} 个自定义 skills")

    return all_skills


__all__ = ["SkillLoader", "FrontmatterParser", "InlineMetadataParser", "load_skills_from_dir"]

