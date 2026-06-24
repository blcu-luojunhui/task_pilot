"""Chat HTTP API：会话 CRUD + 发送消息（驱动 chat turn）+ PRD 提炼。

流式响应不在这里实现——前端拿到 ``trace_id`` 后直接复用 ``/api/task_events/<trace_id>``
SSE 即可消费 token_delta/turn_end 等事件。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from quart import Blueprint, jsonify, request

from src.api.middleware.trace import get_current_trace_id
from src.api.v1.utils import ApiDependencies
from src.core.auth import get_current_account_id
from src.core.chat import ChatRepository, ConversationStatus
from src.core.chat.agent_task import run_chat_turn
from src.core.chat.cancel import ChatCancelRegistry

from src.infra.shared import ErrorCode

logger = logging.getLogger(__name__)

_CHAT_TASK_NAME = "chat.agent_turn"
_DEFAULT_LIST_LIMIT = 20
_MAX_LIST_LIMIT = 100
_DEFAULT_MESSAGE_LIMIT = 200
_MAX_MESSAGE_LIMIT = 500


def _bad_request(message: str) -> tuple:
    return jsonify({"code": ErrorCode.VALIDATION_ERROR, "message": message}), 400


def _not_found(message: str) -> tuple:
    return jsonify({"code": 404, "message": message}), 404


def create_chat_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("chat", __name__)

    def _repo() -> ChatRepository:
        account_id = get_current_account_id() or 0
        return ChatRepository(deps.mysql, account_id=account_id)

    @bp.route("/chat/conversations", methods=["POST"])
    async def create_conversation():
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        title = body.get("title")
        metadata = body.get("metadata")
        if title is not None and not isinstance(title, str):
            return _bad_request("title must be a string")
        if metadata is not None and not isinstance(metadata, dict):
            return _bad_request("metadata must be an object")

        conv = await _repo().create_conversation(title=title, metadata=metadata)
        return jsonify({"code": 0, "data": conv})

    @bp.route("/chat/conversations", methods=["GET"])
    async def list_conversations():
        args = request.args
        try:
            limit = min(max(1, int(args.get("limit", _DEFAULT_LIST_LIMIT))), _MAX_LIST_LIMIT)
        except (TypeError, ValueError):
            limit = _DEFAULT_LIST_LIMIT
        try:
            offset = max(0, int(args.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0

        status_arg = args.get("status")
        if status_arg is None or status_arg == "":
            status = ConversationStatus.ACTIVE.value
        elif status_arg.lower() == "all":
            status = None
        else:
            try:
                status = int(status_arg)
            except ValueError:
                return _bad_request("status must be an integer or 'all'")

        total, items = await _repo().list_conversations(
            limit=limit, offset=offset, status=status
        )
        return jsonify(
            {
                "code": 0,
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": items,
                },
            }
        )

    @bp.route("/chat/conversations/<conversation_id>", methods=["GET"])
    async def get_conversation(conversation_id: str):
        args = request.args
        try:
            msg_limit = min(
                max(1, int(args.get("message_limit", _DEFAULT_MESSAGE_LIMIT))),
                _MAX_MESSAGE_LIMIT,
            )
        except (TypeError, ValueError):
            msg_limit = _DEFAULT_MESSAGE_LIMIT
        before_id = args.get("before_id")
        before_id_int = None
        if before_id:
            try:
                before_id_int = int(before_id)
            except ValueError:
                return _bad_request("before_id must be an integer")

        repo = _repo()
        conv = await repo.get_conversation(conversation_id)
        if not conv:
            return _not_found("conversation not found")
        messages = await repo.list_messages(
            conversation_id, limit=msg_limit, before_id=before_id_int
        )
        return jsonify(
            {
                "code": 0,
                "data": {
                    "conversation": conv,
                    "messages": messages,
                },
            }
        )

    @bp.route("/chat/conversations/<conversation_id>", methods=["PATCH"])
    async def update_conversation(conversation_id: str):
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        title = body.get("title")
        if title is None or not isinstance(title, str):
            return _bad_request("title is required and must be a string")
        ok = await _repo().update_conversation_title(conversation_id, title)
        if not ok:
            return _not_found("conversation not found")
        return jsonify({"code": 0, "data": {"conversation_id": conversation_id, "title": title}})

    @bp.route("/chat/conversations/<conversation_id>", methods=["DELETE"])
    async def delete_conversation(conversation_id: str):
        ok = await _repo().delete_conversation(conversation_id)
        if not ok:
            return _not_found("conversation not found")
        return jsonify({"code": 0, "data": {"conversation_id": conversation_id, "deleted": True}})

    @bp.route("/chat/conversations/<conversation_id>/messages", methods=["POST"])
    async def send_message(conversation_id: str):
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        user_message = (body.get("user_message") or "").strip()
        if not user_message:
            return _bad_request("user_message is required")

        repo = _repo()
        conv = await repo.get_conversation(conversation_id)
        if not conv:
            return _not_found("conversation not found")
        if int(conv.get("status", 0)) == ConversationStatus.DELETED.value:
            return _bad_request("conversation has been deleted")

        trace_id = get_current_trace_id()
        account_id = get_current_account_id() or 0
        try:
            deps.events.ensure_trace(trace_id, metadata={"task_name": _CHAT_TASK_NAME, "account_id": account_id})
        except Exception:
            pass

        asyncio.create_task(
            run_chat_turn(
                db=deps.mysql,
                log=deps.log,
                config=deps.config,
                events=deps.events,
                trace_id=trace_id,
                account_id=account_id,
                conversation_id=conversation_id,
                user_message=user_message,
            ),
            name=f"chat-turn-{trace_id}",
        )

        return jsonify(
            {
                "code": 0,
                "message": "chat turn started",
                "trace_id": trace_id,
                "data": {
                    "trace_id": trace_id,
                    "conversation_id": conversation_id,
                },
            }
        )

    @bp.route("/chat/conversations/<conversation_id>/cancel", methods=["POST"])
    async def cancel_turn(conversation_id: str):
        """取消指定 trace_id 的当前轮次。"""
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        trace_id = body.get("trace_id")
        if not trace_id:
            return _bad_request("trace_id is required")

        account_id = get_current_account_id() or 0
        success = ChatCancelRegistry.cancel(trace_id)
        if not success:
            from src.jobs import TaskScheduler
            scheduler_data = {"task_name": _CHAT_TASK_NAME, "trace_id": trace_id}
            scheduler = TaskScheduler(scheduler_data, trace_id, deps, account_id=account_id)
            success = await scheduler.cancel_task(trace_id)
        return jsonify(
            {
                "code": 0 if success else 1,
                "message": "cancel requested" if success else "task not found or already finished",
                "data": {
                    "conversation_id": conversation_id,
                    "trace_id": trace_id,
                },
            }
        )

    @bp.route("/chat/conversations/<conversation_id>/prd_from_messages", methods=["POST"])
    async def prd_from_messages(conversation_id: str):
        """从选中的聊天消息提炼 PRD。"""
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        message_ids = body.get("message_ids")
        if not message_ids or not isinstance(message_ids, list):
            return _bad_request("message_ids is required and must be a list of integers")
        if not all(isinstance(mid, int) for mid in message_ids):
            return _bad_request("message_ids must be a list of integers")

        repo = _repo()
        conv = await repo.get_conversation(conversation_id)
        if not conv:
            return _not_found("conversation not found")

        # 拉取全部消息，筛选选中的
        messages = await repo.list_messages(conversation_id, limit=_MAX_MESSAGE_LIMIT)
        selected = [m for m in messages if int(m.get("id", 0)) in message_ids]
        if not selected:
            return _bad_request("no matching messages found for the given message_ids")

        # 构建对话 transcript
        transcript_parts: list[str] = []
        for m in selected:
            role = m.get("role", "unknown")
            content = (m.get("content") or "").strip()
            if content:
                transcript_parts.append(f"[{role}]: {content}")
        context = "\n\n".join(transcript_parts)

        if not context.strip():
            return _bad_request("selected messages contain no text content")

        # 调用 LLM 提炼 PRD
        from src.core.agent_task.prompts import PRD_COMPILER_SYSTEM_PROMPT
        from src.core.agents.capabilities.llm.base import LLMMessage, LLMConfig
        from src.core.agents.capabilities.llm.providers import (
            OpenAIProvider,
            ClaudeProvider,
            DeepSeekProvider,
        )

        llm_cfg = deps.config.llm

        def _infer_key(base_url):
            if not base_url:
                return "deepseek"
            bl = base_url.lower()
            if "anthropic" in bl or "claude" in bl:
                return "claude"
            if "deepseek" in bl:
                return "deepseek"
            return "openai"

        key = _infer_key(llm_cfg.base_url)
        defaults = {
            "openai": {"model": "gpt-4o", "base_url": "https://api.openai.com/v1"},
            "claude": {"model": "claude-sonnet-4-6", "base_url": "https://api.anthropic.com/v1"},
            "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
        }
        provider_map = {
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
            "deepseek": DeepSeekProvider,
        }
        provider_dflt = defaults.get(key, defaults["deepseek"])
        provider_cls = provider_map.get(key, DeepSeekProvider)
        llm_config = LLMConfig(
            api_key=llm_cfg.api_key,
            model=llm_cfg.model or provider_dflt["model"],
            base_url=llm_cfg.base_url or provider_dflt["base_url"],
            temperature=0.3,
        )
        provider = provider_cls(llm_config)

        try:
            llm_messages = [
                LLMMessage(role="system", content=PRD_COMPILER_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=f"Based on the following conversation context, create a detailed PRD:\n\n{context}",
                ),
            ]
            response = await provider.chat(messages=llm_messages, temperature=0.3)
            prd = (response.content or "").strip()
            return jsonify({"code": 0, "data": {"prd": prd}})
        except Exception:
            logger.exception("PRD from messages failed for conversation=%s", conversation_id)
            return jsonify({"code": ErrorCode.INTERNAL_ERROR, "message": "PRD generation failed"}), 500
        finally:
            try:
                await provider.close()
            except Exception:
                pass

    return bp


__all__ = ["create_chat_bp"]
