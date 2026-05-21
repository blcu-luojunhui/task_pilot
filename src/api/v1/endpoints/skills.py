from __future__ import annotations

import json
import logging
import os
from collections import Counter

from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies

logger = logging.getLogger(__name__)

# 安全开关：默认禁用直接 skill 调用
_ALLOW_INVOKE = os.environ.get("TASK_PILOT_ALLOW_DIRECT_SKILL_INVOKE", "false").lower() in (
    "true", "1", "yes",
)


async def _collect_24h_calls(deps: ApiDependencies) -> Counter:
    """聚合近 24h 内每个 skill 被调用次数（按 act_start.payload.tool_calls[].name）"""
    rows = await deps.mysql.async_fetch(
        "SELECT payload FROM agent_events "
        "WHERE event_type = 'act_start' "
        "AND created_at > NOW() - INTERVAL 1 DAY"
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


def create_skills_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("skills", __name__)

    @bp.route("/skills", methods=["GET"])
    async def list_skills():
        from src.core.agents.capabilities.skills import get_global_registry

        registry = get_global_registry()
        counts = await _collect_24h_calls(deps)
        skills = []
        for skill in registry.filter(lambda _: True):
            skills.append(
                {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "description": skill.description,
                    "skill_type": skill.skill_type.value,
                    "category": skill.domain or "uncategorized",
                    "risk_level": skill.risk_level.value if skill.risk_level else "READ",
                    "parameters": skill.parameters,
                    "tags": skill.tags,
                    "scope": skill.scope,
                    "call_count_24h": counts.get(skill.name, 0),
                }
            )
        return jsonify({"code": 0, "data": skills})

    @bp.route("/skills/<skill_name>/calls", methods=["GET"])
    async def skill_calls(skill_name: str):
        try:
            limit = min(int(request.args.get("limit", 50)), 100)
        except (TypeError, ValueError):
            limit = 50

        rows = await deps.mysql.async_fetch(
            "SELECT trace_id, sequence, step, payload, created_at "
            "FROM agent_events "
            "WHERE event_type = 'act_start' "
            "AND JSON_CONTAINS(JSON_EXTRACT(payload, '$.tool_calls[*].name'), %s) "
            "ORDER BY created_at DESC LIMIT %s",
            params=(f'"{skill_name}"', limit),
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
                {"code": 403, "message": "Direct skill invoke disabled. Set TASK_PILOT_ALLOW_DIRECT_SKILL_INVOKE=true to enable."}
            ), 403

        from src.core.agents.capabilities.skills import get_global_registry
        from src.core.agents.capabilities.skills.model import RiskLevel
        from src.core.agents.capabilities.skills.context import SkillContext
        from src.core.agents.capabilities.skills.executor import default_executor

        registry = get_global_registry()
        skill = registry.get(skill_name)
        if not skill:
            return jsonify({"code": 404, "message": f"Skill '{skill_name}' not found"}), 404

        # 安全检查：DESTRUCTIVE 永久禁止
        if skill.risk_level == RiskLevel.DESTRUCTIVE:
            return jsonify(
                {"code": 403, "message": f"Skill '{skill_name}' is DESTRUCTIVE — direct invocation forbidden"}
            ), 403

        # 只允许 READ 级别的 skill
        if skill.risk_level != RiskLevel.READ:
            return jsonify(
                {"code": 403, "message": f"Skill '{skill_name}' risk_level={skill.risk_level.value}, only READ allowed"}
            ), 403

        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        params: dict = body.get("params", body.get("parameters", {}))
        if not isinstance(params, dict):
            params = {}

        # 构建上下文
        from src.core.agents.capabilities.skills import MappingResolver
        deps_for_skill = {}
        if hasattr(deps, 'mysql') and deps.mysql:
            deps_for_skill["db"] = deps.mysql
        ctx = SkillContext(_resolver=MappingResolver(deps_for_skill))

        try:
            result = await default_executor.execute(skill, ctx, **params)
            result_str = str(result)
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

    return bp
