"""Skill Store 导入服务 — 从本地文件系统批量导入到 MySQL。

一次性迁移工具：扫描 ~/.claude/skill_hub/ 目录，把每个 skill 目录导入到
skill_registry + skill_files 表。之后所有 CRUD 走 API。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Set

from .parser import SkillMarkdownParser, scan_skill_directory
from .repository import SkillStoreRepository

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = ("_", ".")


class SkillImportService:
    """本地 skill_hub/ 目录 → MySQL 的一次性导入。"""

    def __init__(self, repo: SkillStoreRepository, parser: SkillMarkdownParser | None = None):
        self._repo = repo
        self._parser = parser or SkillMarkdownParser()

    async def preview(self, base_path: str) -> List[Dict]:
        """Dry-run：扫描目录但不写入。返回将要导入的 skill 清单。"""
        base = Path(base_path).expanduser().resolve()
        if not base.is_dir():
            raise FileNotFoundError(f"Skills directory not found: {base}")

        results: List[Dict] = []
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith(_SKIP_PREFIXES):
                continue

            scan = scan_skill_directory(entry, self._parser)
            if scan is None:
                continue

            results.append({
                "dir_name": scan.dir_name,
                "display_name": scan.meta.name or scan.dir_name,
                "description": scan.meta.description[:100] if scan.meta.description else "",
                "files": len(scan.files),
                "keywords": scan.meta.keywords[:5],
                "will_overwrite": False,  # dry-run 不查 DB
            })
        return results

    async def run(
        self,
        base_path: str,
        *,
        source_hint: str = "third-party",
        overwrite: bool = False,
    ) -> Dict:
        """执行导入。

        Args:
            base_path: skill_hub 根目录路径
            source_hint: 来源标记（matt-pocock / arkcli / personal / third-party）
            overwrite: 是否覆盖已存在的 skill（False 则跳过）

        Returns:
            统计信息：{total, imported, skipped, errors}
        """
        base = Path(base_path).expanduser().resolve()
        if not base.is_dir():
            raise FileNotFoundError(f"Skills directory not found: {base}")

        # 获取已存在的 dir_name 集合
        existing_dirs = set()
        if not overwrite:
            rows = await self._repo.get_all_dir_name_to_id()
            existing_dirs = set(rows.keys())

        stats = {"total": 0, "imported": 0, "skipped": 0, "errors": 0, "details": []}

        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if name.startswith(_SKIP_PREFIXES):
                continue

            scan = scan_skill_directory(entry, self._parser)
            if scan is None:
                continue

            stats["total"] += 1

            if name in existing_dirs and not overwrite:
                stats["skipped"] += 1
                stats["details"].append({"dir_name": name, "status": "skipped"})
                continue

            try:
                category_slug = self._infer_category(name, scan)
                source = self._guess_source(base, source_hint)

                if name in existing_dirs:
                    # overwrite: 更新已有 skill
                    existing = await self._repo.get_skill_by_dir(name)
                    if existing:
                        await self._repo.update_skill_from_markdown(
                            existing["id"],
                            _get_primary_content(scan),
                        )
                        skill_id = existing["id"]
                else:
                    skill_id = await self._repo.create_skill_from_markdown(
                        _get_primary_content(scan),
                        source=source,
                        category_slug=category_slug,
                    )

                # 导入其他文件
                for finfo in scan.files:
                    if finfo.is_primary:
                        continue  # SKILL.md 已在上面处理
                    await self._repo.upsert_skill_file(
                        skill_id,
                        relative_path=finfo.relative_path,
                        filename=finfo.filename,
                        file_type=finfo.file_type,
                        mime_type=finfo.mime_type,
                        content=finfo.content,
                        content_hash=finfo.content_hash,
                        file_size=finfo.file_size,
                        is_primary=False,
                    )

                stats["imported"] += 1
                stats["details"].append({"dir_name": name, "status": "imported", "skill_id": skill_id})

            except Exception as exc:
                logger.exception("Failed to import skill: %s", name)
                stats["errors"] += 1
                stats["details"].append({
                    "dir_name": name, "status": "error", "error": str(exc),
                })

        # 在所有 skill 入库后解析依赖关系
        if stats["imported"] > 0:
            await self._resolve_dependencies(base)

        logger.info(
            "Import complete: total=%d imported=%d skipped=%d errors=%d",
            stats["total"], stats["imported"], stats["skipped"], stats["errors"],
        )
        return stats

    async def _resolve_dependencies(self, base: Path) -> None:
        """解析跨 skill 的 Markdown 链接，写入 skill_dependencies。"""
        import re

        name_to_id = await self._repo.get_all_dir_name_to_id()
        if not name_to_id:
            return

        for dir_name, skill_id in name_to_id.items():
            await self._repo.delete_skill_dependencies(skill_id)

            files = await self._repo.get_skill_files(skill_id)
            for f in files:
                content = f.get("content") or ""
                if not content:
                    continue
                refs = re.findall(r'\[([^\]]*)\]\(\.\./([^/]+)/([^)]+)\)', content)
                for _label, target_dir, target_file in refs:
                    if target_dir in name_to_id and target_dir != dir_name:
                        await self._repo.upsert_dependency(
                            source_skill_id=skill_id,
                            target_skill_id=name_to_id[target_dir],
                            relation_type="references",
                            reference_path=f"../{target_dir}/{target_file}",
                        )

    def _guess_source(self, base: Path, fallback: str) -> str:
        spath = str(base)
        if "arkcli" in spath.lower():
            return "arkcli"
        if "matt-pocock" in spath.lower() or "matt_pocock" in spath.lower():
            return "matt-pocock"
        return fallback

    async def run_flat(
        self,
        base_path: str,
        *,
        source_hint: str = "personal",
        category_slug: str | None = None,
        overwrite: bool = False,
    ) -> Dict:
        """从扁平 .md 文件目录导入（每个 .md 文件即一个 skill）。

        适用于 src/infra/skill_hub/ 这类非 Claude Code skill 目录结构。

        Args:
            base_path: 包含 .md 文件的根目录（递归扫描）
            source_hint: 来源标记
            category_slug: 固定分类，None 则从 frontmatter 推断
            overwrite: 是否覆盖已存在的 skill

        Returns:
            统计信息：{total, imported, skipped, errors}
        """
        base = Path(base_path).expanduser().resolve()
        if not base.is_dir():
            raise FileNotFoundError(f"Directory not found: {base}")

        existing_dirs = set()
        if not overwrite:
            rows = await self._repo.get_all_dir_name_to_id()
            existing_dirs = set(rows.keys())

        stats = {"total": 0, "imported": 0, "skipped": 0, "errors": 0, "details": []}

        for md_file in sorted(base.rglob("*.md")):
            if md_file.name.startswith("_") or md_file.name.startswith("."):
                continue
            if ".git" in md_file.parts or "__pycache__" in md_file.parts:
                continue

            stats["total"] += 1

            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                stats["errors"] += 1
                stats["details"].append({
                    "dir_name": md_file.name, "status": "error", "error": str(exc),
                })
                continue

            meta = self._parser.parse_frontmatter(content)
            dir_name = meta.name.strip() or md_file.stem
            if not dir_name:
                stats["errors"] += 1
                stats["details"].append({
                    "dir_name": md_file.name, "status": "error", "error": "无法解析 skill 名称",
                })
                continue

            # 规范化 dir_name
            import re
            dir_name_slug = dir_name.lower().strip()
            dir_name_slug = re.sub(r"[^\w\-]+", "-", dir_name_slug)
            dir_name_slug = re.sub(r"-{2,}", "-", dir_name_slug).strip("-") or dir_name

            if dir_name_slug in existing_dirs:
                if not overwrite:
                    stats["skipped"] += 1
                    stats["details"].append({"dir_name": dir_name_slug, "status": "skipped"})
                    continue
                # overwrite
                existing = await self._repo.get_skill_by_dir(dir_name_slug)
                if existing:
                    try:
                        await self._repo.update_skill_from_markdown(existing["id"], content)
                        stats["imported"] += 1
                        stats["details"].append({
                            "dir_name": dir_name_slug, "status": "imported",
                            "skill_id": existing["id"],
                        })
                    except Exception as exc:
                        stats["errors"] += 1
                        stats["details"].append({
                            "dir_name": dir_name_slug, "status": "error", "error": str(exc),
                        })
                    continue

            try:
                # 从父目录名推断 category
                inferred_category = category_slug
                if not inferred_category:
                    parent = md_file.parent.name.lower()
                    if parent not in ("skill_hub", "skills", ".", "src"):
                        inferred_category = parent

                skill_id = await self._repo.create_skill_from_markdown(
                    content,
                    source=source_hint,
                    category_slug=inferred_category,
                )
                stats["imported"] += 1
                stats["details"].append({
                    "dir_name": dir_name_slug, "status": "imported", "skill_id": skill_id,
                })
                existing_dirs.add(dir_name_slug)
            except ValueError as exc:
                stats["skipped"] += 1
                stats["details"].append({
                    "dir_name": dir_name_slug, "status": "skipped", "error": str(exc),
                })
            except Exception as exc:
                logger.exception("Failed to import flat skill: %s", dir_name_slug)
                stats["errors"] += 1
                stats["details"].append({
                    "dir_name": dir_name_slug, "status": "error", "error": str(exc),
                })

        logger.info(
            "Flat import complete: total=%d imported=%d skipped=%d errors=%d",
            stats["total"], stats["imported"], stats["skipped"], stats["errors"],
        )
        return stats

    def _infer_category(self, dir_name: str, scan) -> str | None:
        fm_category = scan.meta.raw_frontmatter.get("category", "").strip()
        if fm_category:
            return fm_category
        if dir_name.startswith("arkcli-"):
            return "arkcli"
        known = {
            "engineering": {"diagnose", "grill-me", "grill-with-docs", "triage",
                            "improve-codebase-architecture", "tdd", "to-issues", "to-prd",
                            "zoom-out", "prototype", "review", "setup-matt-pocock-skill_hub",
                            "caveman", "handoff", "write-a-skill",
                            "git-guardrails-claude-code", "setup-pre-commit",
                            "migrate-to-shoehorn", "scaffold-exercises",
                            "design-an-interface", "qa", "request-refactor-plan",
                            "code-review-excellence"},
            "personal": {"edit-article", "writing-beats", "writing-fragments", "writing-shape",
                         "obsidian-vault", "my-coffee", "stephen-curry-perspective",
                         "zhang-yiming-perspective", "learn", "huashu-nuwa"},
            "productivity": {"rag-knowledge", "web-research", "global-search",
                             "zhihu-search", "hot-list", "tech-design-doc", "write-prd"},
        }
        for slug, names in known.items():
            if dir_name in names:
                return slug
        return "general"


def _get_primary_content(scan) -> str:
    """从 scan 中取 SKILL.md 的完整内容。"""
    for finfo in scan.files:
        if finfo.is_primary and finfo.content:
            return finfo.content
    # fallback：拼接 frontmatter + body
    fm = scan.meta.raw_frontmatter
    body = scan.meta.body or ""
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.extend(["---", "", body])
    return "\n".join(lines)


__all__ = ["SkillImportService"]
