"""Skill Store API — MySQL 为 skill 唯一事实源。

完整 CRUD：
  POST   /skill-store/skill_hub           创建 skill（上传 Markdown）
  PUT    /skill-store/skill_hub/<dir_name> 更新 skill 内容
  DELETE /skill-store/skill_hub/<dir_name> 删除 skill

搜索与浏览：
  GET    /skill-store/skill_hub           列表（分页 + 过滤）
  GET    /skill-store/skill_hub/search    全文搜索
  GET    /skill-store/skill_hub/<dir_name> 详情（含文件树 + 依赖图）
  GET    /skill-store/skill_hub/<dir_name>/dependencies  依赖图

导入（管理员）：
  POST   /skill-store/import           从本地目录批量导入
  GET    /skill-store/import/preview   预览将要导入的 skill

标签管理：
  POST   /skill-store/skill_hub/<dir_name>/tags       添加标签
  DELETE /skill-store/skill_hub/<dir_name>/tags/<tag>  删除标签

辅助：
  GET    /skill-store/stats            仪表盘统计
  GET    /skill-store/categories       分类列表
  GET    /skill-store/tags             标签云
"""

from __future__ import annotations

import asyncio
import logging
import os

from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies
from src.core.skill_store import SkillStoreRepository, SkillImportService

logger = logging.getLogger(__name__)

_DEFAULT_SKILLS_PATH = os.path.expanduser("~/.claude/skills")


def create_skill_store_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("skill_store", __name__, url_prefix="/skill-store")
    repo = SkillStoreRepository(deps.mysql)
    import_svc = SkillImportService(repo)

    # ── 序列化辅助 ──────────────────────────────────────

    def _skill_row(row: dict) -> dict:
        fm = row.get("frontmatter")
        if isinstance(fm, str):
            try:
                import json as _json
                fm = _json.loads(fm)
            except Exception:
                fm = {}
        return {
            "id": row["id"],
            "dir_name": row["dir_name"],
            "display_name": row.get("display_name") or row["dir_name"],
            "description": row.get("description") or "",
            "version": row.get("version"),
            "frontmatter": fm if isinstance(fm, dict) else {},
            "category": row.get("category_slug") or "general",
            "status": row.get("status", "active"),
            "source": row.get("source", "third-party"),
            "file_count": row.get("file_count", 0),
            "total_size_bytes": row.get("total_size_bytes", 0),
            "content_hash": row.get("content_hash"),
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        }

    # ════════════════════════════════════════════════════
    # 仪表盘
    # ════════════════════════════════════════════════════

    @bp.route("/stats", methods=["GET"])
    async def stats():
        data = await repo.get_stats()
        return jsonify({"code": 0, "data": data})

    # ════════════════════════════════════════════════════
    # 分类 & 标签（辅助查询）
    # ════════════════════════════════════════════════════

    @bp.route("/categories", methods=["GET"])
    async def list_categories():
        rows = await repo.list_categories()
        return jsonify({"code": 0, "data": rows})

    @bp.route("/tags", methods=["GET"])
    async def list_tags():
        rows = await repo.list_all_tags()
        return jsonify({"code": 0, "data": rows})

    # ════════════════════════════════════════════════════
    # Skill CRUD
    # ════════════════════════════════════════════════════

    @bp.route("/skill_hub", methods=["GET"])
    async def list_skills():
        category = request.args.get("category")
        status = request.args.get("status")
        source = request.args.get("source")
        tag = request.args.get("tag")
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(max(1, int(request.args.get("page_size", 20))), 100)
        sort = request.args.get("sort", "updated_at")

        rows, total = await repo.list_skills(
            category_slug=category, status=status, source=source,
            tag=tag, page=page, page_size=page_size, sort=sort,
        )
        items = [_skill_row(r) for r in rows]
        for item in items:
            item["keywords"] = await repo.get_skill_keywords(item["id"])
            item["tags"] = await repo.get_skill_tags(item["id"])

        return jsonify({
            "code": 0,
            "data": {"items": items, "total": total, "page": page, "page_size": page_size},
        })

    @bp.route("/skill_hub", methods=["POST"])
    async def create_skill():
        """上传 Markdown 创建新 skill。

        Request body: {"content": "<SKILL.md 完整内容>", "source": "personal"}
        """
        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown") or ""
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 400, "message": "content 字段是必需的（完整的 SKILL.md Markdown）"}), 400

        source = body.get("source", "personal")
        category = body.get("category")

        try:
            skill_id = await repo.create_skill_from_markdown(
                content, source=source, category_slug=category,
            )
        except ValueError as exc:
            return jsonify({"code": 409, "message": str(exc)}), 409
        except Exception as exc:
            logger.exception("Failed to create skill")
            return jsonify({"code": 500, "message": f"创建失败: {exc}"}), 500

        row = await repo.get_skill_by_id(skill_id)
        item = _skill_row(row) if row else {}
        return jsonify({"code": 0, "data": item})

    @bp.route("/skill_hub/<dir_name>", methods=["GET"])
    async def get_skill(dir_name: str):
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404

        item = _skill_row(row)
        files = await repo.get_skill_files(item["id"])
        item["files"] = [
            {
                "relative_path": f["relative_path"],
                "filename": f["filename"],
                "file_type": f["file_type"],
                "mime_type": f["mime_type"],
                "content": f.get("content") if f.get("file_type") in (
                    "skill_md", "reference", "example", "readme", "script"
                ) else None,
                "content_hash": f["content_hash"],
                "file_size": f["file_size"],
                "is_primary": bool(f["is_primary"]),
            }
            for f in files
        ]
        deps = await repo.get_dependencies(item["id"])
        item["dependencies"] = {
            "forward": [
                {"dir_name": d["dir_name"], "display_name": d["display_name"],
                 "relation_type": d["relation_type"], "reference_path": d.get("reference_path")}
                for d in deps["forward"]
            ],
            "reverse": [
                {"dir_name": d["dir_name"], "display_name": d["display_name"],
                 "relation_type": d["relation_type"], "reference_path": d.get("reference_path")}
                for d in deps["reverse"]
            ],
        }
        item["keywords"] = await repo.get_skill_keywords(item["id"])
        item["tags"] = await repo.get_skill_tags(item["id"])

        return jsonify({"code": 0, "data": item})

    @bp.route("/skill_hub/<dir_name>", methods=["PUT"])
    async def update_skill(dir_name: str):
        """更新 skill 的 Markdown 内容。"""
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown") or ""
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 400, "message": "content 字段是必需的"}), 400

        try:
            ok = await repo.update_skill_from_markdown(row["id"], content)
        except Exception as exc:
            logger.exception("Failed to update skill")
            return jsonify({"code": 500, "message": f"更新失败: {exc}"}), 500

        if not ok:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        updated = await repo.get_skill_by_dir(dir_name)
        return jsonify({"code": 0, "data": _skill_row(updated) if updated else {}})

    @bp.route("/skill_hub/<dir_name>", methods=["DELETE"])
    async def delete_skill(dir_name: str):
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404

        hard = request.args.get("hard", "false").lower() in ("true", "1", "yes")
        if hard:
            await repo.delete_skill(row["id"])
        else:
            await repo.soft_delete_skill(row["id"])
        return jsonify({"code": 0, "data": {"dir_name": dir_name, "deleted": True, "hard": hard}})

    # ════════════════════════════════════════════════════
    # 搜索
    # ════════════════════════════════════════════════════

    @bp.route("/skill_hub/search", methods=["GET"])
    async def search_skills():
        q = request.args.get("q", "")
        category = request.args.get("category")
        tag = request.args.get("tag")
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(max(1, int(request.args.get("page_size", 20))), 100)

        rows, total = await repo.search(q, category_slug=category, tag=tag, page=page, page_size=page_size)
        items = [_skill_row(r) for r in rows]
        for item in items:
            item["keywords"] = await repo.get_skill_keywords(item["id"])
            item["tags"] = await repo.get_skill_tags(item["id"])

        return jsonify({
            "code": 0,
            "data": {"items": items, "total": total, "page": page, "page_size": page_size},
        })

    # ════════════════════════════════════════════════════
    # 依赖图
    # ════════════════════════════════════════════════════

    @bp.route("/skill_hub/<dir_name>/dependencies", methods=["GET"])
    async def skill_dependencies(dir_name: str):
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404
        deps = await repo.get_dependencies(row["id"])
        return jsonify({
            "code": 0,
            "data": {
                "dir_name": dir_name,
                "forward": [
                    {"dir_name": d["dir_name"], "display_name": d["display_name"],
                     "relation_type": d["relation_type"]}
                    for d in deps["forward"]
                ],
                "reverse": [
                    {"dir_name": d["dir_name"], "display_name": d["display_name"],
                     "relation_type": d["relation_type"]}
                    for d in deps["reverse"]
                ],
            },
        })

    # ════════════════════════════════════════════════════
    # 标签管理
    # ════════════════════════════════════════════════════

    @bp.route("/skill_hub/<dir_name>/tags", methods=["POST"])
    async def add_skill_tag(dir_name: str):
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404
        try:
            body = await request.get_json()
            tag = (body or {}).get("tag", "")
        except Exception:
            tag = ""
        if not tag or not isinstance(tag, str):
            return jsonify({"code": 400, "message": "tag is required"}), 400
        await repo.add_tag(row["id"], tag.strip())
        tags = await repo.get_skill_tags(row["id"])
        return jsonify({"code": 0, "data": {"dir_name": dir_name, "tags": tags}})

    @bp.route("/skill_hub/<dir_name>/tags/<tag>", methods=["DELETE"])
    async def remove_skill_tag(dir_name: str, tag: str):
        row = await repo.get_skill_by_dir(dir_name)
        if not row:
            return jsonify({"code": 404, "message": f"Skill '{dir_name}' 不存在"}), 404
        await repo.remove_tag(row["id"], tag)
        tags = await repo.get_skill_tags(row["id"])
        return jsonify({"code": 0, "data": {"dir_name": dir_name, "tags": tags}})

    # ════════════════════════════════════════════════════
    # 导入：本地文件系统 → MySQL（管理员，一次性）
    # ════════════════════════════════════════════════════

    from src.core.auth.decorators import require_role

    @bp.route("/import/preview", methods=["GET"])
    async def import_preview():
        base_path = request.args.get("base_path", _DEFAULT_SKILLS_PATH)
        try:
            items = await import_svc.preview(base_path)
        except FileNotFoundError as exc:
            return jsonify({"code": 404, "message": str(exc)}), 404
        return jsonify({"code": 0, "data": {"base_path": base_path, "count": len(items), "items": items}})

    @bp.route("/import", methods=["POST"])
    @require_role("admin")
    async def import_skills():
        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}
        base_path = body.get("base_path") or _DEFAULT_SKILLS_PATH
        overwrite = body.get("overwrite", False)
        source = body.get("source", "third-party")

        result = await asyncio.to_thread(
            _run_import, import_svc, base_path, source, overwrite,
        )
        return jsonify({"code": 0, "data": result})

    return bp


def _run_import(import_svc: SkillImportService, base_path: str, source: str, overwrite: bool) -> dict:
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            import_svc.run(base_path, source_hint=source, overwrite=overwrite)
        )
    finally:
        loop.close()
