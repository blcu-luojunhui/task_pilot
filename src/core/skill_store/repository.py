"""Skill Store 数据访问层 — MySQL 是 skill 的唯一事实源。

原生 SQL + AsyncMySQLPool，遵循项目 Repository 模式。

核心模型：外部传入 Markdown 字符串（SKILL.md 格式，含 YAML frontmatter），
Repository 负责解析、计算 hash、写入 skill_store_registry + skill_store_files。
"""

from __future__ import annotations

import hashlib
import json as _json
from typing import Any, Dict, List, Optional

from src.infra.database import AsyncMySQLPool
from .parser import SkillMarkdownParser, ParsedSkillMeta


class SkillStoreRepository:
    """Skill Store 全部数据库操作。"""

    def __init__(self, db: AsyncMySQLPool, parser: SkillMarkdownParser | None = None):
        self._db = db
        self._parser = parser or SkillMarkdownParser()

    # ═══════════════════════════════════════════════════════
    # Categories
    # ═══════════════════════════════════════════════════════

    async def list_categories(self) -> List[Dict[str, Any]]:
        rows = await self._db.async_fetch(
            """SELECT c.id, c.slug, c.name, c.description, c.sort_order,
                      COUNT(r.id) AS skill_count
               FROM skill_store_categories c
               LEFT JOIN skill_store_registry r ON r.category_id = c.id
               GROUP BY c.id
               ORDER BY c.sort_order"""
        )
        return rows

    async def get_category_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            "SELECT id, slug, name, description, sort_order FROM skill_store_categories WHERE slug = %s",
            params=(slug,),
        )

    # ═══════════════════════════════════════════════════════
    # Skills — 查询
    # ═══════════════════════════════════════════════════════

    async def list_skills(
        self,
        *,
        category_slug: str | None = None,
        status: str | None = None,
        source: str | None = None,
        tag: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "updated_at",
    ) -> tuple[List[Dict[str, Any]], int]:
        where = ["1=1"]
        params: List[Any] = []

        if category_slug:
            where.append("c.slug = %s")
            params.append(category_slug)
        if status:
            where.append("r.status = %s")
            params.append(status)
        if source:
            where.append("r.source = %s")
            params.append(source)
        if tag:
            where.append("r.id IN (SELECT sk.skill_id FROM skill_store_tags sk WHERE sk.tag = %s)")
            params.append(tag)

        where_clause = " AND ".join(where)
        sort_col = "r.updated_at" if sort not in ("dir_name", "file_count") else f"r.{sort}"
        sort_dir = "DESC" if sort in ("updated_at", "file_count") else "ASC"

        count_row = await self._db.async_fetch_one(
            f"SELECT COUNT(*) AS total FROM skill_store_registry r "
            f"LEFT JOIN skill_store_categories c ON r.category_id = c.id "
            f"WHERE {where_clause}",
            params=tuple(params),
        )
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        params.extend([page_size, offset])
        rows = await self._db.async_fetch(
            f"""SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                       r.frontmatter, r.status, r.source, r.file_count, r.total_size_bytes,
                       c.slug AS category_slug, c.name AS category_name,
                       r.content_hash, r.created_at, r.updated_at
                FROM skill_store_registry r
                LEFT JOIN skill_store_categories c ON r.category_id = c.id
                WHERE {where_clause}
                ORDER BY {sort_col} {sort_dir}
                LIMIT %s OFFSET %s""",
            params=tuple(params),
        )
        return rows, total

    async def get_skill_by_dir(self, dir_name: str) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            """SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                      r.frontmatter, r.status, r.source, r.file_count, r.total_size_bytes,
                      c.slug AS category_slug, c.name AS category_name,
                      r.content_plain, r.content_hash, r.created_at, r.updated_at
               FROM skill_store_registry r
               LEFT JOIN skill_store_categories c ON r.category_id = c.id
               WHERE r.dir_name = %s""",
            params=(dir_name,),
        )

    async def get_skill_by_id(self, skill_id: int) -> Optional[Dict[str, Any]]:
        return await self._db.async_fetch_one(
            """SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                      r.frontmatter, r.status, r.source, r.file_count, r.total_size_bytes,
                      c.slug AS category_slug, c.name AS category_name,
                      r.content_plain, r.content_hash, r.created_at, r.updated_at
               FROM skill_store_registry r
               LEFT JOIN skill_store_categories c ON r.category_id = c.id
               WHERE r.id = %s""",
            params=(skill_id,),
        )

    async def get_skill_files(self, skill_id: int) -> List[Dict[str, Any]]:
        return await self._db.async_fetch(
            """SELECT id, relative_path, filename, file_type, mime_type,
                      content, content_hash, file_size, is_primary, updated_at
               FROM skill_store_files
               WHERE skill_id = %s
               ORDER BY is_primary DESC, relative_path ASC""",
            params=(skill_id,),
        )

    async def get_skill_keywords(self, skill_id: int) -> List[str]:
        rows = await self._db.async_fetch(
            "SELECT keyword FROM skill_store_keywords WHERE skill_id = %s ORDER BY keyword",
            params=(skill_id,),
        )
        return [r["keyword"] for r in rows]

    async def get_skill_tags(self, skill_id: int) -> List[str]:
        rows = await self._db.async_fetch(
            "SELECT tag FROM skill_store_tags WHERE skill_id = %s ORDER BY tag",
            params=(skill_id,),
        )
        return [r["tag"] for r in rows]

    async def get_all_dir_name_to_id(self) -> Dict[str, int]:
        rows = await self._db.async_fetch("SELECT id, dir_name FROM skill_store_registry")
        return {r["dir_name"]: r["id"] for r in rows}

    # ═══════════════════════════════════════════════════════
    # Skills — 以 Markdown 为中心的 CRUD
    # ═══════════════════════════════════════════════════════

    async def create_skill_from_markdown(
        self,
        content: str,
        *,
        source: str = "personal",
        category_slug: str | None = None,
    ) -> int:
        """上传一段 SKILL.md 格式的 Markdown，解析后创建 skill + 文件记录。返回 skill_id。

        Args:
            content: 完整的 SKILL.md 内容（含 YAML frontmatter）
            source: 来源标记
            category_slug: 分类 slug，None 则从 frontmatter 推断或默认 general

        Raises:
            ValueError: dir_name 已存在
        """
        meta = self._parser.parse_frontmatter(content)
        dir_name = self._resolve_dir_name(meta)
        content_hash = self._parser.sha256(content)

        existing = await self._db.async_fetch_one(
            "SELECT id FROM skill_store_registry WHERE dir_name = %s",
            params=(dir_name,),
        )
        if existing:
            raise ValueError(f"Skill '{dir_name}' 已存在（id={existing['id']}）")

        category_id = None
        slug = category_slug or self._infer_category(dir_name, meta)
        if slug:
            cat = await self.get_category_by_slug(slug)
            if cat:
                category_id = cat["id"]

        file_size = len(content.encode("utf-8"))

        skill_id = await self._db.async_save(
            """INSERT INTO skill_store_registry
               (dir_name, display_name, description, version, frontmatter,
                category_id, status, source, file_count, total_size_bytes,
                content_plain, content_hash)
               VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, 1, %s, %s, %s)""",
            (
                dir_name,
                meta.name or dir_name,
                meta.description or "",
                meta.version or "",
                _json.dumps(meta.raw_frontmatter, ensure_ascii=False),
                category_id,
                source,
                file_size,
                content,           # content_plain = SKILL.md 原文（FULLTEXT 用）
                content_hash,
            ),
            return_lastrowid=True,
        )

        # 写入文件记录（仅 SKILL.md）
        await self._db.async_save(
            """INSERT INTO skill_store_files
               (skill_id, relative_path, filename, file_type, mime_type,
                content, content_hash, file_size, is_primary)
               VALUES (%s, 'SKILL.md', 'SKILL.md', 'skill_md', 'text/markdown',
                %s, %s, %s, 1)""",
            (skill_id, content, content_hash, file_size),
        )

        # 写入关键词
        if meta.keywords:
            await self._set_keywords(skill_id, meta.keywords)

        return skill_id

    async def update_skill_from_markdown(self, skill_id: int, content: str) -> bool:
        """用新的 Markdown 内容更新已有 skill。返回是否成功。"""
        meta = self._parser.parse_frontmatter(content)
        content_hash = self._parser.sha256(content)
        file_size = len(content.encode("utf-8"))

        # 更新 registry
        affected = await self._db.async_save(
            """UPDATE skill_store_registry
               SET display_name = %s, description = %s, version = %s,
                   frontmatter = %s, content_plain = %s, content_hash = %s,
                   total_size_bytes = %s, file_count = 1
               WHERE id = %s""",
            (
                meta.name or "",
                meta.description or "",
                meta.version or "",
                _json.dumps(meta.raw_frontmatter, ensure_ascii=False),
                content,
                content_hash,
                file_size,
                skill_id,
            ),
        )
        if not affected:
            return False

        # upsert SKILL.md 文件记录
        await self._db.async_save(
            """INSERT INTO skill_store_files
               (skill_id, relative_path, filename, file_type, mime_type,
                content, content_hash, file_size, is_primary)
               VALUES (%s, 'SKILL.md', 'SKILL.md', 'skill_md', 'text/markdown',
                %s, %s, %s, 1)
               ON DUPLICATE KEY UPDATE
               content = VALUES(content),
               content_hash = VALUES(content_hash),
               file_size = VALUES(file_size)""",
            (skill_id, content, content_hash, file_size),
        )

        # 更新关键词
        if meta.keywords:
            await self._set_keywords(skill_id, meta.keywords)

        return True

    async def rename_skill(self, skill_id: int, new_dir_name: str) -> bool:
        """重命名 skill 的 dir_name。"""
        existing = await self._db.async_fetch_one(
            "SELECT id FROM skill_store_registry WHERE dir_name = %s",
            params=(new_dir_name,),
        )
        if existing and int(existing["id"]) != skill_id:
            raise ValueError(f"dir_name '{new_dir_name}' 已被占用")

        affected = await self._db.async_save(
            "UPDATE skill_store_registry SET dir_name = %s WHERE id = %s",
            (new_dir_name, skill_id),
        )
        return affected > 0

    async def delete_skill(self, skill_id: int) -> bool:
        """硬删除（CASCADE 会自动清理 files/keywords/tags/dependencies）。"""
        affected = await self._db.async_save(
            "DELETE FROM skill_store_registry WHERE id = %s", (skill_id,)
        )
        return affected > 0

    async def soft_delete_skill(self, skill_id: int) -> bool:
        affected = await self._db.async_save(
            "UPDATE skill_store_registry SET status = 'deprecated' WHERE id = %s",
            (skill_id,),
        )
        return affected > 0

    # ═══════════════════════════════════════════════════════
    # Files — 用于批量导入
    # ═══════════════════════════════════════════════════════

    async def upsert_skill_file(
        self,
        skill_id: int,
        *,
        relative_path: str,
        filename: str,
        file_type: str,
        mime_type: str,
        content: str | None,
        content_hash: str,
        file_size: int,
        is_primary: bool,
    ) -> None:
        await self._db.async_save(
            """INSERT INTO skill_store_files
               (skill_id, relative_path, filename, file_type, mime_type,
                content, content_hash, file_size, is_primary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
               filename = VALUES(filename), file_type = VALUES(file_type),
               mime_type = VALUES(mime_type), content = VALUES(content),
               content_hash = VALUES(content_hash), file_size = VALUES(file_size),
               is_primary = VALUES(is_primary)""",
            (skill_id, relative_path, filename, file_type, mime_type,
             content, content_hash, file_size, 1 if is_primary else 0),
        )

    async def delete_skill_files(self, skill_id: int) -> int:
        return await self._db.async_save(
            "DELETE FROM skill_store_files WHERE skill_id = %s", (skill_id,)
        )

    async def get_stale_file_paths(self, skill_id: int, current_paths: List[str]) -> List[str]:
        if not current_paths:
            rows = await self._db.async_fetch(
                "SELECT relative_path FROM skill_store_files WHERE skill_id = %s",
                params=(skill_id,),
            )
            return [r["relative_path"] for r in rows]
        placeholders = ",".join(["%s"] * len(current_paths))
        rows = await self._db.async_fetch(
            f"""SELECT relative_path FROM skill_store_files
                WHERE skill_id = %s AND relative_path NOT IN ({placeholders})""",
            params=(skill_id, *current_paths),
        )
        return [r["relative_path"] for r in rows]

    async def delete_file_by_path(self, skill_id: int, relative_path: str) -> bool:
        affected = await self._db.async_save(
            "DELETE FROM skill_store_files WHERE skill_id = %s AND relative_path = %s",
            (skill_id, relative_path),
        )
        return affected > 0

    # ═══════════════════════════════════════════════════════
    # Keywords
    # ═══════════════════════════════════════════════════════

    async def _set_keywords(self, skill_id: int, keywords: List[str]) -> None:
        """替换式写入 frontmatter 关键词。"""
        await self._db.async_save(
            "DELETE FROM skill_store_keywords WHERE skill_id = %s AND source = 'frontmatter_keywords'",
            (skill_id,),
        )
        for kw in keywords:
            kw = kw.strip()[:128]
            if not kw:
                continue
            try:
                await self._db.async_save(
                    "INSERT INTO skill_store_keywords (skill_id, keyword, source) VALUES (%s, %s, 'frontmatter_keywords')",
                    (skill_id, kw),
                )
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════
    # Tags
    # ═══════════════════════════════════════════════════════

    async def add_tag(self, skill_id: int, tag: str) -> None:
        try:
            await self._db.async_save(
                "INSERT INTO skill_store_tags (skill_id, tag) VALUES (%s, %s)",
                (skill_id, tag.strip()[:64]),
            )
        except Exception:
            pass

    async def remove_tag(self, skill_id: int, tag: str) -> bool:
        affected = await self._db.async_save(
            "DELETE FROM skill_store_tags WHERE skill_id = %s AND tag = %s",
            (skill_id, tag.strip()),
        )
        return affected > 0

    async def set_tags(self, skill_id: int, tags: List[str]) -> None:
        await self._db.async_save("DELETE FROM skill_store_tags WHERE skill_id = %s", (skill_id,))
        for t in tags:
            await self.add_tag(skill_id, t)

    async def list_all_tags(self) -> List[Dict[str, Any]]:
        return await self._db.async_fetch(
            """SELECT tag, COUNT(*) AS skill_count
               FROM skill_store_tags GROUP BY tag
               ORDER BY skill_count DESC, tag ASC"""
        )

    # ═══════════════════════════════════════════════════════
    # Dependencies
    # ═══════════════════════════════════════════════════════

    async def get_dependencies(self, skill_id: int) -> Dict[str, List[Dict[str, Any]]]:
        forward = await self._db.async_fetch(
            """SELECT r.dir_name, r.display_name, d.relation_type, d.reference_path
               FROM skill_store_dependencies d
               JOIN skill_store_registry r ON r.id = d.target_skill_id
               WHERE d.source_skill_id = %s
               ORDER BY d.relation_type, r.dir_name""",
            params=(skill_id,),
        )
        reverse = await self._db.async_fetch(
            """SELECT r.dir_name, r.display_name, d.relation_type, d.reference_path
               FROM skill_store_dependencies d
               JOIN skill_store_registry r ON r.id = d.source_skill_id
               WHERE d.target_skill_id = %s
               ORDER BY d.relation_type, r.dir_name""",
            params=(skill_id,),
        )
        return {"forward": forward, "reverse": reverse}

    async def upsert_dependency(
        self, source_skill_id: int, target_skill_id: int, relation_type: str, reference_path: str | None
    ) -> None:
        try:
            await self._db.async_save(
                """INSERT INTO skill_store_dependencies
                   (source_skill_id, target_skill_id, relation_type, reference_path)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE reference_path = VALUES(reference_path)""",
                (source_skill_id, target_skill_id, relation_type, reference_path),
            )
        except Exception:
            pass

    async def delete_skill_dependencies(self, skill_id: int) -> int:
        return await self._db.async_save(
            "DELETE FROM skill_store_dependencies WHERE source_skill_id = %s OR target_skill_id = %s",
            (skill_id, skill_id),
        )

    # ═══════════════════════════════════════════════════════
    # Search
    # ═══════════════════════════════════════════════════════

    async def search(
        self,
        query: str,
        *,
        category_slug: str | None = None,
        tag: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Dict[str, Any]], int]:
        where_parts = ["r.status = 'active'"]
        where_params: List[Any] = []
        order_params: List[Any] = []
        order_clause = "ORDER BY r.updated_at DESC"

        if category_slug:
            where_parts.append("c.slug = %s")
            where_params.append(category_slug)
        if tag:
            where_parts.append("r.id IN (SELECT sk.skill_id FROM skill_store_tags sk WHERE sk.tag = %s)")
            where_params.append(tag)

        if query.strip():
            q = query.strip()
            where_parts.append("MATCH(r.content_plain) AGAINST(%s IN BOOLEAN MODE)")
            where_params.append(q)
            order_clause = (
                "ORDER BY MATCH(r.content_plain) AGAINST(%s IN BOOLEAN MODE) DESC, r.updated_at DESC"
            )
            order_params.append(q)

        where_clause = " AND ".join(where_parts)

        count_row = await self._db.async_fetch_one(
            f"SELECT COUNT(*) AS total FROM skill_store_registry r "
            f"LEFT JOIN skill_store_categories c ON r.category_id = c.id "
            f"WHERE {where_clause}",
            params=tuple(where_params),
        )
        total = count_row["total"] if count_row else 0

        offset = (page - 1) * page_size
        select_params: List[Any] = where_params + order_params + [page_size, offset]
        rows = await self._db.async_fetch(
            f"""SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                       r.frontmatter, r.status, r.source, r.file_count, r.total_size_bytes,
                       c.slug AS category_slug, c.name AS category_name,
                       r.content_hash, r.created_at, r.updated_at
                FROM skill_store_registry r
                LEFT JOIN skill_store_categories c ON r.category_id = c.id
                WHERE {where_clause}
                {order_clause}
                LIMIT %s OFFSET %s""",
            params=tuple(select_params),
        )
        return rows, total

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """精确触发词匹配（Agent 运行时用）。"""
        return await self._db.async_fetch(
            """SELECT r.id, r.dir_name, r.display_name, r.description,
                      c.slug AS category_slug
               FROM skill_store_registry r
               JOIN skill_store_keywords k ON k.skill_id = r.id
               LEFT JOIN skill_store_categories c ON r.category_id = c.id
               WHERE k.keyword = %s AND r.status = 'active'
               ORDER BY r.dir_name
               LIMIT %s""",
            params=(keyword, limit),
        )

    # ═══════════════════════════════════════════════════════
    # Agent 启动时批量加载
    # ═══════════════════════════════════════════════════════

    async def load_all_for_agent(self, domain: str | None = None) -> List[Dict[str, Any]]:
        """Agent 启动时从 DB 加载全部 skill。返回 registry 可用的结构。

        每行 = skill 主记录 + SKILL.md 的完整内容（从 skill_store_files 中取 is_primary=1 的行）。
        """
        if domain:
            rows = await self._db.async_fetch(
                """SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                          r.frontmatter, r.status, r.source,
                          c.slug AS category_slug,
                          f.content AS skill_md_content
                   FROM skill_store_registry r
                   LEFT JOIN skill_store_categories c ON r.category_id = c.id
                   LEFT JOIN skill_store_files f ON f.skill_id = r.id AND f.is_primary = 1
                   WHERE r.status = 'active' AND c.slug = %s
                   ORDER BY r.dir_name""",
                params=(domain,),
            )
        else:
            rows = await self._db.async_fetch(
                """SELECT r.id, r.dir_name, r.display_name, r.description, r.version,
                          r.frontmatter, r.status, r.source,
                          c.slug AS category_slug,
                          f.content AS skill_md_content
                   FROM skill_store_registry r
                   LEFT JOIN skill_store_categories c ON r.category_id = c.id
                   LEFT JOIN skill_store_files f ON f.skill_id = r.id AND f.is_primary = 1
                   WHERE r.status = 'active'
                   ORDER BY r.dir_name""",
            )
        return rows

    # ═══════════════════════════════════════════════════════
    # Stats
    # ═══════════════════════════════════════════════════════

    async def get_stats(self) -> Dict[str, Any]:
        total = await self._db.async_fetch_one(
            "SELECT COUNT(*) AS n FROM skill_store_registry WHERE status = 'active'"
        )
        by_source = await self._db.async_fetch(
            "SELECT source, COUNT(*) AS n FROM skill_store_registry WHERE status = 'active' GROUP BY source"
        )
        by_category = await self._db.async_fetch(
            """SELECT c.slug, c.name, COUNT(r.id) AS n
               FROM skill_store_categories c
               LEFT JOIN skill_store_registry r ON r.category_id = c.id AND r.status = 'active'
               GROUP BY c.id ORDER BY c.sort_order"""
        )
        total_files = await self._db.async_fetch_one(
            "SELECT SUM(file_count) AS n, SUM(total_size_bytes) AS s FROM skill_store_registry WHERE status = 'active'"
        )
        return {
            "total_skills": total["n"] if total else 0,
            "by_source": {r["source"]: r["n"] for r in by_source},
            "by_category": {r["slug"]: {"name": r["name"], "count": r["n"]} for r in by_category},
            "total_files": total_files["n"] if total_files else 0,
            "total_size_bytes": total_files["s"] if total_files else 0,
        }

    # ═══════════════════════════════════════════════════════
    # 内部工具
    # ═══════════════════════════════════════════════════════

    def _resolve_dir_name(self, meta: ParsedSkillMeta) -> str:
        """从 frontmatter name 推导 dir_name。"""
        name = meta.name.strip()
        if not name:
            raise ValueError("SKILL.md frontmatter 缺少 name 字段")
        # 转小写、空格替换为连字符
        import re
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\-]+", "-", slug)
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug or name

    def _infer_category(self, dir_name: str, meta: ParsedSkillMeta) -> str | None:
        """从目录名 / frontmatter 推断分类 slug。"""
        # frontmatter 显式声明的 category
        fm_category = meta.raw_frontmatter.get("category", "").strip()
        if fm_category:
            return fm_category
        # arkcli 前缀
        if dir_name.startswith("arkcli-"):
            return "arkcli"
        # 已知分类的 skill 列表
        known = {
            "engineering": {"diagnose", "grill-me", "grill-with-docs", "triage",
                            "improve-codebase-architecture", "tdd", "to-issues", "to-prd",
                            "zoom-out", "prototype", "review", "setup-matt-pocock-skills",
                            "caveman", "handoff", "write-a-skill",
                            "git-guardrails-claude-code", "setup-pre-commit",
                            "migrate-to-shoehorn", "scaffold-exercises", "ubiquitous-language",
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


__all__ = ["SkillStoreRepository"]
