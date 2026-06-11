from __future__ import annotations

import json
import logging
import os
from collections import Counter

from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies
from src.core.auth import get_current_account_id
from src.core.skills import (
    PersonalSkillRepository,
    SystemSkillRepository,
    default_personal_skill_template,
    extract_personal_fields,
    skill_to_markdown,
)

logger = logging.getLogger(__name__)

# 安全开关：默认禁用直接 skill 调用
_ALLOW_INVOKE = os.environ.get("TASK_PILOT_ALLOW_DIRECT_SKILL_INVOKE", "false").lower() in (
    "true",
    "1",
    "yes",
)


async def _collect_24h_calls(deps: ApiDependencies, account_id: int) -> Counter:
    """聚合近 24h 内每个 skill 被调用次数（按 act_start.payload.tool_calls[].name）"""
    rows = await deps.mysql.async_fetch(
        "SELECT payload FROM agent_events "
        "WHERE event_type = 'act_start' "
        "AND account_id = %s "
        "AND created_at > NOW() - INTERVAL 1 DAY",
        params=(account_id,),
    )
    counter: Counter = Counter()
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if not isinstance(payload, dict):
            continue
        for tc in payload.get("tool_calls", []) or []:
            name = tc.get("name") if isinstance(tc, dict) else None
            if name:
                counter[name] += 1
    return counter


def _infer_category(skill) -> str:
    """按 domain / 命名前缀推断 category 文件夹。"""
    domain = (skill.domain or "").strip()
    if domain and domain != "general":
        return domain

    name = skill.name or ""
    if name.startswith("db_"):
        return "database"
    if name.startswith("http_"):
        return "http"
    if name.startswith("task_"):
        return "task"
    if name.startswith("util_") or name == "write_file":
        return "utils"
    if name in {"plan_tasks", "run_task", "list_recent_tasks", "escalate_to_agent"}:
        return "chat_ops"
    return "general"


def _serialize_system_skill(skill, counts: Counter) -> dict:
    category = _infer_category(skill)
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "skill_type": skill.skill_type.value,
        "category": category,
        "risk_level": skill.risk_level.value if skill.risk_level else "read",
        "parameters": skill.parameters,
        "tags": skill.tags,
        "scope": skill.scope,
        "call_count_24h": counts.get(skill.name, 0),
        "source": "system",
        "editable": False,
        "markdown": skill_to_markdown(skill),
    }


def _serialize_personal_skill(row: dict) -> dict:
    return {
        "skill_id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description") or "",
        "skill_type": "knowledge",
        "category": row.get("category") or "general",
        "risk_level": "read",
        "parameters": {},
        "tags": [],
        "scope": row.get("scope") or "agent:*",
        "call_count_24h": 0,
        "source": "personal",
        "editable": True,
        "markdown": row.get("content") or "",
    }


def _serialize_system_skill_row(row: dict) -> dict:
    return {
        "skill_id": str(row["id"]),
        "name": row["name"],
        "description": row.get("description") or "",
        "skill_type": row.get("skill_type") or "knowledge",
        "category": row.get("category") or "general",
        "risk_level": "read",
        "parameters": {},
        "tags": [],
        "scope": row.get("scope") or "agent:*",
        "call_count_24h": 0,
        "source": "system",
        "editable": True,
        "markdown": row.get("content") or "",
    }


def _extract_guidelines(content: str) -> list[str]:
    lines = content.splitlines()
    in_section = False
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and "guideline" in stripped.lower():
            in_section = True
            continue
        if in_section and stripped.startswith("##"):
            break
        if in_section and stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def create_skills_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("skills", __name__)
    personal_repo = PersonalSkillRepository(deps.mysql)
    system_repo = SystemSkillRepository(deps.mysql)

    @bp.route("/skills", methods=["GET"])
    async def list_skills():
        from src.core.agents.capabilities.skills import get_global_registry

        registry = get_global_registry()
        account_id = get_current_account_id() or 0
        counts = await _collect_24h_calls(deps, account_id)

        skills = [_serialize_system_skill(skill, counts) for skill in registry.filter(lambda _: True)]

        if account_id:
            try:
                personal_rows = await personal_repo.list_by_account(account_id)
                skills.extend(_serialize_personal_skill(row) for row in personal_rows)
            except Exception:
                logger.exception("Failed to load personal skills for account_id=%s", account_id)

        return jsonify({"code": 0, "data": skills})

    @bp.route("/skills/personal/template", methods=["GET"])
    async def personal_skill_template():
        name = request.args.get("name", "new-skill")
        category = request.args.get("category", "chat_ops")
        return jsonify(
            {
                "code": 0,
                "data": {
                    "markdown": default_personal_skill_template(name, category),
                },
            }
        )

    @bp.route("/skills/personal", methods=["POST"])
    async def create_personal_skill():
        account_id = get_current_account_id()
        if not account_id:
            return jsonify({"code": 401, "message": "未登录"}), 401

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown")
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 1001, "message": "content is required"}), 400

        fields = extract_personal_fields(content)
        try:
            skill_id = await personal_repo.create(
                account_id,
                name=fields["name"],
                category=fields["category"],
                description=fields["description"],
                scope=fields["scope"],
                content=content,
            )
            row = await personal_repo.get_by_id(account_id, skill_id)
        except Exception as exc:
            logger.exception("Create personal skill failed")
            if "Duplicate" in str(exc) or "uk_account_skill_name" in str(exc):
                return jsonify({"code": 1002, "message": f"Skill '{fields['name']}' 已存在"}), 409
            return jsonify({"code": 500, "message": f"创建失败: {exc}"}), 500

        return jsonify({"code": 0, "data": _serialize_personal_skill(row)})

    @bp.route("/skills/personal/<int:skill_id>", methods=["PUT"])
    async def update_personal_skill(skill_id: int):
        account_id = get_current_account_id()
        if not account_id:
            return jsonify({"code": 401, "message": "未登录"}), 401

        existing = await personal_repo.get_by_id(account_id, skill_id)
        if not existing:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown")
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 1001, "message": "content is required"}), 400

        fields = extract_personal_fields(content)
        updated = await personal_repo.update(
            account_id,
            skill_id,
            name=fields["name"],
            category=fields["category"],
            description=fields["description"],
            scope=fields["scope"],
            content=content,
        )
        if not updated:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        row = await personal_repo.get_by_id(account_id, skill_id)
        return jsonify({"code": 0, "data": _serialize_personal_skill(row)})

    @bp.route("/skills/personal/<int:skill_id>", methods=["DELETE"])
    async def delete_personal_skill(skill_id: int):
        account_id = get_current_account_id()
        if not account_id:
            return jsonify({"code": 401, "message": "未登录"}), 401

        deleted = await personal_repo.delete(account_id, skill_id)
        if not deleted:
            return jsonify({"code": 404, "message": "Skill not found"}), 404
        return jsonify({"code": 0, "data": {"deleted": True, "skill_id": str(skill_id)}})

    @bp.route("/skills/<skill_name>/calls", methods=["GET"])
    async def skill_calls(skill_name: str):
        try:
            limit = min(int(request.args.get("limit", 50)), 100)
        except (TypeError, ValueError):
            limit = 50

        account_id = get_current_account_id() or 0
        rows = await deps.mysql.async_fetch(
            "SELECT trace_id, sequence, step, payload, created_at "
            "FROM agent_events "
            "WHERE event_type = 'act_start' "
            "AND account_id = %s "
            "AND JSON_CONTAINS(JSON_EXTRACT(payload, '$.tool_calls[*].name'), %s) "
            "ORDER BY created_at DESC LIMIT %s",
            params=(account_id, f'"{skill_name}"', limit),
        )

        calls = []
        for row in rows:
            payload = row.get("payload")
            if isinstance(payload, str):
                payload = json.loads(payload)
            tool_calls = (payload or {}).get("tool_calls", [])
            matched = next(
                (tc for tc in tool_calls if tc.get("name") == skill_name),
                None,
            )
            calls.append(
                {
                    "trace_id": row["trace_id"],
                    "sequence": row["sequence"],
                    "step": row.get("step"),
                    "arguments": matched.get("arguments") if matched else None,
                    "created_at": str(row["created_at"]),
                }
            )

        return jsonify({"code": 0, "data": {"skill_name": skill_name, "calls": calls}})

    @bp.route("/skills/<skill_name>/invoke", methods=["POST"])
    async def invoke_skill(skill_name: str):
        if not _ALLOW_INVOKE:
            return jsonify(
                {
                    "code": 403,
                    "message": "Direct skill invoke disabled. Set TASK_PILOT_ALLOW_DIRECT_SKILL_INVOKE=true to enable.",
                }
            ), 403

        from src.core.agents.capabilities.skills import get_global_registry
        from src.core.agents.capabilities.skills.model import RiskLevel
        from src.core.agents.capabilities.skills.context import SkillContext
        from src.core.agents.capabilities.skills.executor import default_executor

        registry = get_global_registry()
        skill = registry.get(skill_name)
        if not skill:
            return jsonify({"code": 404, "message": f"Skill '{skill_name}' not found"}), 404

        if skill.risk_level == RiskLevel.DESTRUCTIVE:
            return jsonify(
                {
                    "code": 403,
                    "message": f"Skill '{skill_name}' is DESTRUCTIVE — direct invocation forbidden",
                }
            ), 403

        if skill.risk_level != RiskLevel.READ:
            return jsonify(
                {
                    "code": 403,
                    "message": f"Skill '{skill_name}' risk_level={skill.risk_level.value}, only READ allowed",
                }
            ), 403

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        params: dict = body.get("params", body.get("parameters", {}))
        if not isinstance(params, dict):
            params = {}

        from src.core.agents.capabilities.skills import MappingResolver

        deps_for_skill = {}
        if hasattr(deps, "mysql") and deps.mysql:
            deps_for_skill["db"] = deps.mysql
        ctx = SkillContext(_resolver=MappingResolver(deps_for_skill))

        try:
            result = await default_executor.execute(skill, ctx, **params)
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "skill_name": skill_name,
                        "result": str(result),
                        "success": True,
                    },
                }
            )
        except Exception as e:
            logger.exception("Skill invoke failed: %s", skill_name)
            return jsonify(
                {
                    "code": 500,
                    "message": f"Invoke failed: {e}",
                    "data": {"skill_name": skill_name, "result": str(e), "success": False},
                }
            )

    # ── Admin: 系统 Skills CRUD ─────────────────────────────

    from src.core.auth.decorators import require_role
    from src.core.agents.capabilities.skills import get_global_registry
    from src.core.agents.capabilities.skills.model import Skill

    @bp.route("/skills/system", methods=["POST"])
    @require_role("admin")
    async def create_system_skill():
        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown")
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 1001, "message": "content is required"}), 400

        fields = extract_personal_fields(content)
        try:
            skill_id = await system_repo.create(
                name=fields["name"],
                category=fields["category"],
                description=fields["description"],
                scope=fields["scope"],
                content=content,
            )
            row = await system_repo.get_by_id(skill_id)
        except Exception as exc:
            logger.exception("Create system skill failed")
            if "Duplicate" in str(exc):
                return jsonify({"code": 1002, "message": f"Skill '{fields['name']}' 已存在"}), 409
            return jsonify({"code": 500, "message": f"创建失败: {exc}"}), 500

        # 注册到全局 registry
        registry = get_global_registry()
        skill = Skill.knowledge(
            name=fields["name"],
            description=fields["description"],
            domain=fields["category"],
            scope=fields["scope"],
            content=body.get("detail") or fields.get("body", ""),
            guidelines=_extract_guidelines(content),
        )
        registry.register(skill)

        return jsonify({"code": 0, "data": _serialize_system_skill_row(row)})

    @bp.route("/skills/system/<int:skill_id>", methods=["PUT"])
    @require_role("admin")
    async def update_system_skill(skill_id: int):
        existing = await system_repo.get_by_id(skill_id)
        if not existing:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        content = body.get("content") or body.get("markdown")
        if not isinstance(content, str) or not content.strip():
            return jsonify({"code": 1001, "message": "content is required"}), 400

        fields = extract_personal_fields(content)
        updated = await system_repo.update(
            skill_id,
            name=fields["name"],
            category=fields["category"],
            description=fields["description"],
            scope=fields["scope"],
            content=content,
        )
        if not updated:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        # 更新 registry
        registry = get_global_registry()
        registry.unregister(existing["name"])
        skill = Skill.knowledge(
            name=fields["name"],
            description=fields["description"],
            domain=fields["category"],
            scope=fields["scope"],
            content=body.get("detail") or fields.get("body", ""),
            guidelines=_extract_guidelines(content),
        )
        registry.register(skill)

        row = await system_repo.get_by_id(skill_id)
        return jsonify({"code": 0, "data": _serialize_system_skill_row(row)})

    @bp.route("/skills/system/<int:skill_id>", methods=["DELETE"])
    @require_role("admin")
    async def delete_system_skill(skill_id: int):
        existing = await system_repo.get_by_id(skill_id)
        if not existing:
            return jsonify({"code": 404, "message": "Skill not found"}), 404

        await system_repo.delete(skill_id)

        # 从 registry 移除
        registry = get_global_registry()
        registry.unregister(existing["name"])

        return jsonify({"code": 0, "data": {"deleted": True, "skill_id": str(skill_id)}})

    return bp
