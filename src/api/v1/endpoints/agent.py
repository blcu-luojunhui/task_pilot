"""Agent Run API：POST /api/agent/run — 目标驱动 agent 执行。

前端拿到 trace_id 后通过 SSE ``/api/task_events/<trace_id>`` 消费实时事件。
"""
from __future__ import annotations

import logging
import json
import time
from typing import Any, Dict, Optional

from quart import Blueprint, jsonify, request

from src.api.middleware.trace import get_current_trace_id
from src.api.v1.utils import ApiDependencies
from src.core.agent_task.prompts import PRD_COMPILER_SYSTEM_PROMPT
from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig, LLMMessage
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider,
    ClaudeProvider,
    DeepSeekProvider,
)
from src.core.auth import get_current_account_id
from src.core.agents.capabilities.skills import RiskLevel, ToolPolicy, ToolPolicyError
from src.core.agents.capabilities.skills.security import redact_sensitive_data
from src.core.agents.runtime.harness import (
    ApprovalDecision,
    ApprovalPolicy,
    ApprovalPolicyError,
    ReconciliationDecision,
    ReconciliationError,
)
from src.core.agents.execution import DBToolExecutionLedger, ToolExecutionLedgerError
from src.infra.shared import ErrorCode
from src.jobs import TaskScheduler
from src.jobs.task_config import TaskStatus

# 触发 run_agent 的 @register 装饰器（统一入口，支持 agent/chat 双模式）
from src.core.agent_task import run_agent as _run_agent  # noqa: F401

_AGENT_TASK_NAME = "agent.run"
_AVAILABLE_TOOL_AREAS = ["database", "http", "task", "utils", "chat_ops"]

_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
}

_PROVIDER_DEFAULTS = {
    "openai": {"model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
    "claude": {
        "model": "claude-sonnet-4-6",
        "base_url": "https://api.anthropic.com/v1",
    },
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
}

logger = logging.getLogger(__name__)


def _infer_provider_key(base_url: Optional[str]) -> str:
    if not base_url:
        return "deepseek"
    bl = base_url.lower()
    if "anthropic" in bl or "claude" in bl:
        return "claude"
    if "deepseek" in bl:
        return "deepseek"
    return "openai"


def _build_llm_provider(cfg) -> LLMProvider:
    key = _infer_provider_key(cfg.base_url)
    defaults = _PROVIDER_DEFAULTS.get(key, _PROVIDER_DEFAULTS["deepseek"])
    provider_cls = _PROVIDER_MAP.get(key, DeepSeekProvider)
    llm_config = LLMConfig(
        api_key=cfg.api_key,
        model=cfg.model or defaults["model"],
        base_url=cfg.base_url or defaults["base_url"],
        temperature=cfg.temperature,
    )
    logger.info("agent endpoint 使用 provider=%s model=%s", key, llm_config.model)
    return provider_cls(llm_config)


def _bad_request(message: str) -> tuple:
    return jsonify({"code": ErrorCode.VALIDATION_ERROR, "message": message}), 400


def create_agent_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("agent", __name__)

    @bp.route("/agent/tool_areas", methods=["GET"])
    async def list_tool_areas():
        """返回可用的工具区域列表，供前端技能选择器使用。"""
        return jsonify(
            {
                "code": 0,
                "data": {
                    "tool_areas": _AVAILABLE_TOOL_AREAS,
                },
            }
        )

    @bp.route("/agent/generate_prd", methods=["POST"])
    async def generate_prd():
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        goal = (body.get("goal") or "").strip()

        if not goal:
            return _bad_request("goal is required and must be a non-empty string")

        llm_cfg = deps.config.llm
        provider = _build_llm_provider(llm_cfg)

        try:
            messages = [
                LLMMessage(role="system", content=PRD_COMPILER_SYSTEM_PROMPT),
                LLMMessage(role="user", content=goal),
            ]
            response = await provider.chat(
                messages=messages,
                temperature=0.3,
            )
            prd = response.content.strip()
            return jsonify({"code": 0, "data": {"prd": prd}})
        except Exception:
            logger.exception("PRD 生成失败")
            return jsonify({"code": ErrorCode.INTERNAL_ERROR, "message": "PRD 生成失败，请稍后重试"}), 500
        finally:
            try:
                await provider.close()
            except Exception:
                pass

    @bp.route("/agent/run", methods=["POST"])
    async def run_agent():
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        goal = (body.get("goal") or "").strip()
        tool_areas = body.get("tool_areas") or []

        if not goal:
            return _bad_request("goal is required and must be a non-empty string")
        if not isinstance(tool_areas, list) or not all(isinstance(a, str) for a in tool_areas):
            return _bad_request("tool_areas must be a list of strings")

        try:
            tool_policy = ToolPolicy.from_mapping(
                body.get("tool_policy"),
                default_risk_levels=(RiskLevel.READ,),
            )
            approval_policy = ApprovalPolicy.from_mapping(body.get("approval_policy"))
        except (ToolPolicyError, ApprovalPolicyError) as exc:
            return _bad_request(str(exc))

        max_steps = body.get("max_steps", deps.config.llm.max_steps)
        if not isinstance(max_steps, int) or isinstance(max_steps, bool) or not 1 <= max_steps <= 50:
            return _bad_request("max_steps must be an integer between 1 and 50")

        # 过滤只允许已知工具区域
        safe_areas = [a for a in tool_areas if a in _AVAILABLE_TOOL_AREAS]
        if not safe_areas:
            safe_areas = ["chat_ops", "task"]

        trace_id = get_current_trace_id()
        account_id = get_current_account_id() or 0

        # 预创建 trace，避免前端 SSE 抢跑命中 404
        try:
            deps.events.ensure_trace(
                trace_id,
                metadata={"task_name": _AGENT_TASK_NAME, "goal": goal[:200], "account_id": account_id},
            )
        except Exception:
            pass

        scheduler_data = {
            "task_name": _AGENT_TASK_NAME,
            "goal": goal,
            "tool_areas": safe_areas,
            "original_goal": (body.get("original_goal") or "").strip() or goal,
            "tool_policy": tool_policy.to_dict(),
            "max_steps": max_steps,
            "approval_policy": approval_policy.to_dict(),
        }
        scheduler = TaskScheduler(scheduler_data, trace_id, deps, account_id=account_id)
        result = await scheduler.deal()

        if isinstance(result, dict) and result.get("code") == 0:
            inner = result.get("data") or {}
            return jsonify(
                {
                    "code": 0,
                    "message": inner.get("message") or "agent run started",
                    "trace_id": inner.get("trace_id") or trace_id,
                    "data": {
                        "trace_id": inner.get("trace_id") or trace_id,
                        "tool_areas": safe_areas,
                        "tool_policy": tool_policy.to_dict(),
                        "max_steps": max_steps,
                        "approval_policy": approval_policy.to_dict(),
                    },
                }
            )
        return jsonify(result)

    @bp.route("/agent/runs/<trace_id>/approval", methods=["POST"])
    async def resolve_approval(trace_id: str):
        """Resolve one pending tool approval and resume the durable run."""
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        account_id = get_current_account_id() or 0
        try:
            decision = ApprovalDecision.from_mapping(
                {
                    **body,
                    "actor_id": str(account_id),
                }
            )
        except ApprovalPolicyError as exc:
            return _bad_request(str(exc))
        assert decision is not None
        task = await deps.mysql.async_fetch_one(
            "SELECT task_status, data FROM task_manager "
            "WHERE trace_id = %s AND account_id = %s",
            params=(trace_id, account_id),
        )
        if not task:
            return jsonify({"code": 404, "message": "agent run not found"}), 404
        run_data = task.get("data") or {}
        if isinstance(run_data, (str, bytes, bytearray)):
            try:
                run_data = json.loads(run_data)
            except (TypeError, ValueError):
                return jsonify({"code": 500, "message": "stored checkpoint is invalid"}), 500
        pending = run_data.get("pending_approval") or {}
        if decision.request_id != pending.get("request_id"):
            return _bad_request("request_id does not match pending approval")
        if not run_data.get("checkpoint"):
            return jsonify({"code": 500, "message": "stored checkpoint is missing"}), 500

        resumed_data = {
            **run_data,
            "task_name": _AGENT_TASK_NAME,
            "status": "resuming",
            "approval_decision": decision.to_dict(),
        }
        task_status = int(task.get("task_status", -1))
        recovering_claim = (
            task_status == TaskStatus.INIT
            and run_data.get("status") == "resuming"
            and run_data.get("approval_decision") == decision.to_dict()
        )
        if task_status not in {TaskStatus.WAITING_APPROVAL, TaskStatus.INIT}:
            return jsonify(
                {"code": 409, "message": "agent run is not waiting for approval"}
            ), 409
        if task_status == TaskStatus.INIT and not recovering_claim:
            return jsonify(
                {"code": 409, "message": "approval was already resolved"}
            ), 409
        if not recovering_claim:
            affected = await deps.mysql.async_save(
                "UPDATE task_manager SET task_status = %s, start_timestamp = %s, "
                "finish_timestamp = NULL, data = %s "
                "WHERE trace_id = %s AND account_id = %s AND task_status = %s",
                params=(
                    TaskStatus.INIT,
                    int(time.time()),
                    json.dumps(resumed_data, ensure_ascii=False),
                    trace_id,
                    account_id,
                    TaskStatus.WAITING_APPROVAL,
                ),
            )
            if not affected:
                return jsonify(
                    {"code": 409, "message": "approval was already resolved"}
                ), 409

        last_event = await deps.mysql.async_fetch_one(
            "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM agent_events "
            "WHERE trace_id = %s AND account_id = %s",
            params=(trace_id, account_id),
        )
        deps.events.reopen_trace(
            trace_id,
            metadata={
                "task_name": _AGENT_TASK_NAME,
                "goal": str(run_data.get("goal", ""))[:200],
                "account_id": account_id,
            },
            initial_sequence=int((last_event or {}).get("sequence") or 0),
        )

        scheduler = TaskScheduler(resumed_data, trace_id, deps, account_id=account_id)
        result = await scheduler.deal()
        if isinstance(result, dict) and result.get("code") == 0:
            return jsonify(
                {
                    "code": 0,
                    "message": "approval resolved; agent run resumed",
                    "trace_id": trace_id,
                    "data": {
                        "trace_id": trace_id,
                        "request_id": decision.request_id,
                        "decision": decision.decision,
                        "tool_calls": pending.get("tool_calls", []),
                    },
                }
            )
        # Scheduling can still fail after the CAS claim (for example, concurrency
        # limits). Restore the durable checkpoint so the approval can be retried.
        await deps.mysql.async_save(
            "UPDATE task_manager SET task_status = %s, finish_timestamp = %s, data = %s "
            "WHERE trace_id = %s AND account_id = %s AND task_status = %s",
            params=(
                TaskStatus.WAITING_APPROVAL,
                int(time.time()),
                json.dumps(run_data, ensure_ascii=False),
                trace_id,
                account_id,
                TaskStatus.INIT,
            ),
        )
        deps.events.close_trace(trace_id)
        return jsonify(result)

    @bp.route("/agent/runs/<trace_id>/reconciliation", methods=["POST"])
    async def resolve_reconciliation(trace_id: str):
        """Resolve one ambiguous side effect and resume the durable run."""
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        account_id = get_current_account_id() or 0
        try:
            decision = ReconciliationDecision.from_mapping(
                {**body, "actor_id": str(account_id)}
            )
        except ReconciliationError as exc:
            return _bad_request(str(exc))
        assert decision is not None
        decision = ReconciliationDecision(
            tool_call_id=decision.tool_call_id,
            decision=decision.decision,
            result_content=(
                str(redact_sensitive_data(decision.result_content))
                if decision.result_content is not None
                else None
            ),
            reason=decision.reason,
            actor_id=decision.actor_id,
        )

        task = await deps.mysql.async_fetch_one(
            "SELECT task_status, data FROM task_manager "
            "WHERE trace_id = %s AND account_id = %s",
            params=(trace_id, account_id),
        )
        if not task:
            return jsonify({"code": 404, "message": "agent run not found"}), 404

        run_data = task.get("data") or {}
        if isinstance(run_data, (str, bytes, bytearray)):
            try:
                run_data = json.loads(run_data)
            except (TypeError, ValueError):
                return jsonify({"code": 500, "message": "stored checkpoint is invalid"}), 500
        pending = run_data.get("pending_reconciliation") or {}
        if decision.tool_call_id != pending.get("tool_call_id"):
            return _bad_request("tool_call_id does not match pending reconciliation")
        if not run_data.get("checkpoint"):
            return jsonify({"code": 500, "message": "stored checkpoint is missing"}), 500

        task_status = int(task.get("task_status", -1))
        resumed_data = {
            **run_data,
            "task_name": _AGENT_TASK_NAME,
            "status": "resuming",
            "reconciliation_decision": decision.to_dict(),
        }
        recovering_claim = (
            task_status == TaskStatus.INIT
            and run_data.get("status") == "resuming"
            and run_data.get("reconciliation_decision") == decision.to_dict()
        )
        if task_status not in {TaskStatus.WAITING_RECONCILIATION, TaskStatus.INIT}:
            return jsonify(
                {"code": 409, "message": "agent run is not waiting for reconciliation"}
            ), 409
        if task_status == TaskStatus.INIT and not recovering_claim:
            return jsonify(
                {"code": 409, "message": "reconciliation was already claimed"}
            ), 409

        ledger = DBToolExecutionLedger(deps.mysql, account_id=account_id)
        ledger_result = decision.tool_message_content()
        ledger_error = (
            decision.to_audit_dict().get("reason")
            or "human reconciliation marked execution as failed"
        )
        try:
            await ledger.resolve(
                trace_id,
                decision.tool_call_id,
                decision=decision.decision,
                result_content=ledger_result if decision.decision == "completed" else None,
                error_message=ledger_error,
            )
        except ToolExecutionLedgerError as exc:
            return jsonify({"code": 409, "message": str(exc)}), 409

        if not recovering_claim:
            affected = await deps.mysql.async_save(
                "UPDATE task_manager SET task_status = %s, start_timestamp = %s, "
                "finish_timestamp = NULL, data = %s "
                "WHERE trace_id = %s AND account_id = %s AND task_status = %s",
                params=(
                    TaskStatus.INIT,
                    int(time.time()),
                    json.dumps(resumed_data, ensure_ascii=False),
                    trace_id,
                    account_id,
                    TaskStatus.WAITING_RECONCILIATION,
                ),
            )
            if not affected:
                return jsonify(
                    {"code": 409, "message": "reconciliation was already claimed"}
                ), 409

        last_event = await deps.mysql.async_fetch_one(
            "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM agent_events "
            "WHERE trace_id = %s AND account_id = %s",
            params=(trace_id, account_id),
        )
        deps.events.reopen_trace(
            trace_id,
            metadata={
                "task_name": _AGENT_TASK_NAME,
                "goal": str(run_data.get("goal", ""))[:200],
                "account_id": account_id,
            },
            initial_sequence=int((last_event or {}).get("sequence") or 0),
        )
        scheduler = TaskScheduler(resumed_data, trace_id, deps, account_id=account_id)
        result = await scheduler.deal()
        if isinstance(result, dict) and result.get("code") == 0:
            return jsonify(
                {
                    "code": 0,
                    "message": "reconciliation resolved; agent run resumed",
                    "trace_id": trace_id,
                    "data": {
                        "trace_id": trace_id,
                        "tool_call_id": decision.tool_call_id,
                        "decision": decision.decision,
                    },
                }
            )

        await deps.mysql.async_save(
            "UPDATE task_manager SET task_status = %s, finish_timestamp = %s, data = %s "
            "WHERE trace_id = %s AND account_id = %s AND task_status = %s",
            params=(
                TaskStatus.WAITING_RECONCILIATION,
                int(time.time()),
                json.dumps(run_data, ensure_ascii=False),
                trace_id,
                account_id,
                TaskStatus.INIT,
            ),
        )
        deps.events.close_trace(trace_id)
        return jsonify(result)

    return bp


__all__ = ["create_agent_bp"]
