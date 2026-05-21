"""Chat HTTP API：会话 CRUD + 发送消息（驱动 chat.agent_turn task）。

流式响应不在这里实现——前端拿到 ``trace_id`` 后直接复用 ``/api/task_events/<trace_id>``
SSE 即可消费 think/act/run_end 等事件。
"""
from __future__ import annotations

from typing import Any, Dict

from quart import Blueprint, jsonify, request

from src.api.middleware.trace import get_current_trace_id
from src.api.v1.utils import ApiDependencies
from src.core.chat import ChatRepository, ConversationStatus
from src.core.chat.service import ChatService

# 触发 chat.agent_turn 的 @register 装饰器（此时 src.jobs.__init__ 已完全加载，
# 不会引发循环——agent_task 反向依赖 jobs/api 都安全）
from src.core.chat import agent_task as _chat_agent_task  # noqa: F401

from src.infra.shared import ErrorCode
from src.jobs import TaskScheduler


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
        return ChatRepository(deps.mysql)

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

        # 用 middleware 注入的 trace_id 作为本轮 chat task 的 trace_id；
        # 前端可立即拿它订阅 SSE
        trace_id = get_current_trace_id()
        # 在 task 真正起步前就把 trace 占位到 event bus，
        # 避免前端 SSE 抢跑命中 404 后无限 backoff 重连
        try:
            deps.events.ensure_trace(trace_id, metadata={"task_name": _CHAT_TASK_NAME})
        except Exception:
            pass
        scheduler_data = {
            "task_name": _CHAT_TASK_NAME,
            "conversation_id": conversation_id,
            "user_message": user_message,
        }
        scheduler = TaskScheduler(scheduler_data, trace_id, deps)
        result = await scheduler.deal()

        if isinstance(result, dict) and result.get("code") == 0:
            inner = result.get("data") or {}
            return jsonify(
                {
                    "code": 0,
                    "message": inner.get("message") or "chat turn started",
                    "trace_id": inner.get("trace_id") or trace_id,
                    "data": {
                        "trace_id": inner.get("trace_id") or trace_id,
                        "conversation_id": conversation_id,
                    },
                }
            )
        return jsonify(result)

    @bp.route("/chat/conversations/<conversation_id>/cancel", methods=["POST"])
    async def cancel_turn(conversation_id: str):
        """取消指定 trace_id 的当前轮次。trace_id 由前端 SSE 订阅时拿到。"""
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        trace_id = body.get("trace_id")
        if not trace_id:
            return _bad_request("trace_id is required")

        scheduler_data = {"task_name": _CHAT_TASK_NAME, "trace_id": trace_id}
        scheduler = TaskScheduler(scheduler_data, trace_id, deps)
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

    @bp.route(
        "/chat/conversations/<conversation_id>/confirm", methods=["POST"]
    )
    async def confirm_plan(conversation_id: str):
        body: Dict[str, Any] = await request.get_json(silent=True) or {}
        message_id = body.get("message_id")
        action = body.get("action")

        if not message_id or not isinstance(message_id, int):
            return _bad_request("message_id is required and must be an integer")
        if action not in ("confirm", "reject"):
            return _bad_request("action must be 'confirm' or 'reject'")

        trace_id = get_current_trace_id()
        chat_service = ChatService(
            db=deps.mysql,
            log=deps.log,
            config=deps.config,
            event_bus=deps.events,
        )

        new_trace_id = await chat_service.confirm_plan(
            conversation_id=conversation_id,
            message_id=message_id,
            action=action,
            trace_id=trace_id,
            deps=deps,
        )

        if new_trace_id == "__not_found__":
            return jsonify({
                "code": 404,
                "message": "no pending plan found for this message",
            }), 404
        if new_trace_id is None:
            # reject 成功
            return jsonify({"code": 0, "message": "plan rejected"})

        return jsonify({
            "code": 0,
            "trace_id": new_trace_id,
            "message": "confirmed, execution started",
        })

    return bp


__all__ = ["create_chat_bp"]
