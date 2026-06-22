"""Agent Run API：POST /api/agent/run — 目标驱动 agent 执行。

前端拿到 trace_id 后通过 SSE ``/api/task_events/<trace_id>`` 消费实时事件。
"""
from __future__ import annotations

import logging
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
from src.infra.shared import ErrorCode
from src.jobs import TaskScheduler

# 触发 agent.run_goal 的 @register 装饰器（与 chat.agent_turn 相同模式）
from src.core.agent_task import run_agent_goal as _run_agent_goal  # noqa: F401

_AGENT_TASK_NAME = "agent.run_goal"
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
                    },
                }
            )
        return jsonify(result)

    return bp


__all__ = ["create_agent_bp"]
