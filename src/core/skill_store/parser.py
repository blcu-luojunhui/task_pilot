"""Claude Code Skill Markdown 解析器。

解析 SKILL.md 的 YAML frontmatter、提取触发关键词，
扫描 skill 目录获取文件清单与哈希。
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ParsedSkillMeta:
    """从 SKILL.md frontmatter 解析出的元数据。"""

    name: str = ""
    description: str = ""
    version: str = ""
    keywords: List[str] = field(default_factory=list)
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""


@dataclass
class SkillFileInfo:
    """单个 skill 文件的信息。"""

    relative_path: str
    filename: str
    file_type: str
    mime_type: str
    content: Optional[str]
    content_hash: str
    file_size: int
    is_primary: bool = False


@dataclass
class SkillDirectoryScan:
    """一次 skill 目录扫描的完整结果。"""

    dir_name: str
    files: List[SkillFileInfo]
    meta: ParsedSkillMeta
    total_size: int = 0
    content_plain: str = ""
    content_hash: str = ""


class SkillMarkdownParser:
    """Claude Code SKILL.md 解析器。

    职责：
    - 解析 YAML frontmatter（name / description / version / keywords）
    - 从 description 中提取触发词
    - 推断文件类型
    - 计算 SHA-256
    """

    # frontmatter 字段与 JSON 键的映射
    _FM_NAME = "name"
    _FM_DESCRIPTION = "description"
    _FM_VERSION = "version"
    _FM_KEYWORDS = "keywords"

    # 触发词提取：中文引号 / 英文引号 / 「」包裹的短语
    _TRIGGER_RE = re.compile(r'["""「]([^"""」]+)[""」]')
    # description 中 "Use when" / "触发词" / "触发" 后的冒号分隔短语
    _DESC_TRIGGER_RE = re.compile(r"(?:触发词[：:]?\s*|Use when[：:]?\s*)(.+?)(?:[.。]|$)", re.IGNORECASE)

    # 文件名 → file_type 映射
    _TYPE_BY_FILENAME = {
        "SKILL.md": "skill_md",
        "REFERENCE.md": "reference",
        "EXAMPLES.md": "example",
        "EXAMPLES": "example",
        "manifest.json": "manifest",
        "README.md": "readme",
        "README": "readme",
    }

    _TYPE_BY_EXTENSION = {
        ".py": "script",
        ".sh": "script",
        ".js": "script",
        ".ts": "script",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".gif": "image",
        ".svg": "image",
        ".webp": "image",
    }

    _TEXT_EXTENSIONS = frozenset({".md", ".txt", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".xml", ".html", ".css", ".sql"})

    # ── public API ──────────────────────────────────────────

    def parse_frontmatter(self, content: str) -> ParsedSkillMeta:
        """解析 SKILL.md 的 YAML frontmatter。"""
        text = content.strip()
        if not text.startswith("---"):
            return ParsedSkillMeta(raw_frontmatter={}, body=content)

        lines = text.splitlines()
        if lines[0].strip() != "---":
            return ParsedSkillMeta(raw_frontmatter={}, body=content)

        # 收集 frontmatter 键值对
        frontmatter: Dict[str, Any] = {}
        end_line = len(lines)
        for i in range(1, len(lines)):
            line = lines[i].rstrip()
            if line.strip() == "---":
                end_line = i
                break
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()

        body = "\n".join(lines[end_line + 1:]).strip()

        keywords = self._extract_keywords(frontmatter)
        name = frontmatter.get(self._FM_NAME, "").strip().strip('"').strip("'")
        desc_raw = frontmatter.get(self._FM_DESCRIPTION, "")
        description = self._normalize_description(desc_raw)

        return ParsedSkillMeta(
            name=name,
            description=description,
            version=frontmatter.get(self._FM_VERSION, "").strip().strip('"'),
            keywords=keywords,
            raw_frontmatter=dict(frontmatter),
            body=body,
        )

    def classify_file(self, filename: str) -> str:
        """根据文件名推断 file_type。"""
        # 精确匹配
        if filename in self._TYPE_BY_FILENAME:
            return self._TYPE_BY_FILENAME[filename]
        # 带扩展名的 readme
        if filename.lower().startswith("readme"):
            return "readme"
        # 扩展名匹配
        ext = os.path.splitext(filename)[1].lower()
        if ext in self._TYPE_BY_EXTENSION:
            return self._TYPE_BY_EXTENSION[ext]
        return "other"

    def is_text_file(self, filename: str) -> bool:
        """判断是否为文本文件（应读取内容）。"""
        if filename in ("SKILL.md", "REFERENCE.md", "EXAMPLES.md", "README.md", "manifest.json"):
            return True
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._TEXT_EXTENSIONS

    @staticmethod
    def sha256(content: str | bytes) -> str:
        """计算 SHA-256 哈希。"""
        if isinstance(content, str):
            content = content.encode("utf-8", errors="replace")
        return hashlib.sha256(content).hexdigest()

    # ── private ─────────────────────────────────────────────

    def _extract_keywords(self, frontmatter: Dict[str, Any]) -> List[str]:
        """从 frontmatter 中提取关键词列表。"""
        keywords: List[str] = []

        # 方式 1：显式 keywords 字段（逗号分隔的 YAML 数组样式的字符串）
        raw = frontmatter.get(self._FM_KEYWORDS, "")
        if isinstance(raw, list):
            keywords.extend(str(k).strip() for k in raw if str(k).strip())
        elif isinstance(raw, str) and raw.strip():
            # 尝试解析逗号分隔
            parts = re.split(r"[,\n]", raw)
            keywords.extend(p.strip().strip('"').strip("'") for p in parts if p.strip())

        # 方式 2：从 description 中提取触发词
        desc = frontmatter.get(self._FM_DESCRIPTION, "")
        if isinstance(desc, str):
            # 提取「」或 "" 包裹的短语
            quoted = self._TRIGGER_RE.findall(desc)
            keywords.extend(q.strip() for q in quoted if len(q.strip()) >= 2)

            # 提取 "触发词:" 后的短语
            m = self._DESC_TRIGGER_RE.search(desc)
            if m:
                trigger_text = m.group(1)
                extra = re.split(r"[、,，]", trigger_text)
                keywords.extend(e.strip().strip('"').strip("'") for e in extra if e.strip())

        # 去重 + 排序
        seen: set[str] = set()
        result: List[str] = []
        for kw in keywords:
            kw = kw.strip()
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)
        return result

    def _normalize_description(self, raw: str) -> str:
        """规范化 description：把 YAML 多行字符串展开为单行。"""
        if not raw:
            return ""
        # 去掉 YAML 的 > / | 折叠标记
        text = re.sub(r"^[>|]\s*", "", raw.strip())
        # 合并换行为空格
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def scan_skill_directory(
    dir_path: str | Path,
    parser: SkillMarkdownParser | None = None,
) -> SkillDirectoryScan | None:
    """扫描单个 skill 目录，返回完整结果。

    如果目录没有 SKILL.md，返回 None。
    """
    if parser is None:
        parser = SkillMarkdownParser()

    path = Path(dir_path)
    if not path.is_dir():
        return None

    dir_name = path.name

    # 跳过非 skill 目录
    if dir_name.startswith("_") or dir_name.startswith("."):
        return None

    skill_md_path = path / "SKILL.md"
    if not skill_md_path.is_file():
        return None

    files: List[SkillFileInfo] = []
    content_parts: List[str] = []
    total_size = 0

    for filepath in sorted(path.rglob("*")):
        if not filepath.is_file():
            continue
        if ".git" in filepath.parts or "__pycache__" in filepath.parts:
            continue

        rel = str(filepath.relative_to(path))
        fname = filepath.name
        ftype = parser.classify_file(fname)
        is_text = parser.is_text_file(fname)
        is_primary = fname == "SKILL.md"

        content: Optional[str] = None
        file_hash: str
        fsize = filepath.stat().st_size
        total_size += fsize

        if is_text and fsize < 5 * 1024 * 1024:  # 限制 5MB
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                file_hash = parser.sha256(content)
            except Exception:
                content = None
                file_hash = parser.sha256(filepath.read_bytes())
        else:
            # 二进制文件：只读前 4KB 做 hash
            with open(filepath, "rb") as fh:
                head = fh.read(4096)
            file_hash = parser.sha256(head)

        # 推断 mime_type
        mime = _guess_mime(fname)

        files.append(SkillFileInfo(
            relative_path=rel,
            filename=fname,
            file_type=ftype,
            mime_type=mime,
            content=content,
            content_hash=file_hash,
            file_size=fsize,
            is_primary=is_primary,
        ))

        if is_text and content:
            content_parts.append(content)

        # 最多 200 个文件
        if len(files) >= 200:
            break

    # 解析 SKILL.md 的 frontmatter
    skill_md = next((f for f in files if f.filename == "SKILL.md"), None)
    if skill_md and skill_md.content:
        meta = parser.parse_frontmatter(skill_md.content)
    else:
        meta = ParsedSkillMeta(name=dir_name)

    content_plain = "\n\n".join(content_parts)
    content_hash = parser.sha256(content_plain) if content_plain else ""

    return SkillDirectoryScan(
        dir_name=dir_name,
        files=files,
        meta=meta,
        total_size=total_size,
        content_plain=content_plain,
        content_hash=content_hash,
    )


def _guess_mime(filename: str) -> str:
    """简单 MIME 推断。"""
    ext = os.path.splitext(filename)[1].lower()
    mime_map: Dict[str, str] = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".py": "text/x-python",
        ".sh": "text/x-shellscript",
        ".js": "application/javascript",
        ".ts": "application/typescript",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".toml": "text/toml",
        ".xml": "text/xml",
        ".html": "text/html",
        ".css": "text/css",
        ".sql": "text/sql",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }
    return mime_map.get(ext, "application/octet-stream")


__all__ = ["SkillMarkdownParser", "ParsedSkillMeta", "SkillFileInfo", "SkillDirectoryScan", "scan_skill_directory"]
