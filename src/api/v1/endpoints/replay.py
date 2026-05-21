"""
Replay / Time Travel 端点 — 将历史 trace 的 prompt 重新发给 LLM，对比新旧结果。
"""
from __future__ import annotations

import json
import logging

from quart import Blueprint, jsonify, request

from src.api.v1.utils import ApiDependencies

logger = logging.getLogger(__name__)


def create_replay_bp(deps: ApiDependencies) -> Blueprint:
    bp = Blueprint("replay", __name__)

    @bp.route("/replay", methods=["POST"])
    async def replay_trace():
        try:
            body = await request.get_json()
            body = body or {}
        except Exception:
            body = {}

        trace_id = body.get("trace_id", "")
        if not trace_id:
            return jsonify({"code": 400, "message": "trace_id is required"}), 400

        model = body.get("model")  # optional override

        # 1. 加载 prompt_assembled 事件
        events = await deps.mysql.async_fetch(
            "SELECT sequence, payload FROM agent_events "
            "WHERE trace_id=%s AND event_type='prompt_assembled' "
            "ORDER BY sequence",
            params=(trace_id,),
        )
        if not events:
            return jsonify(
                {"code": 404, "message": "No prompt_assembled events found for replay"}
            ), 404

        # 使用最后一个 prompt（包含完整上下文）
        last_event = events[-1]
        payload = last_event["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        messages_data = payload.get("messages", [])
        tools_spec = payload.get("tools_spec")

        # 2. 构建 LLM provider
        from src.core.agents.capabilities.llm.base import LLMConfig, LLMMessage
        from src.core.agents.capabilities.llm.providers.openai import OpenAIProvider

        llm_config = deps.config.llm
        config = LLMConfig(
            api_key=llm_config.api_key,
            model=model or llm_config.model,
            base_url=llm_config.base_url,
            temperature=0.2,
            max_tokens=llm_config.max_tokens,
            timeout=llm_config.timeout,
        )

        provider = OpenAIProvider(config)

        # 3. 构建消息列表 — 过滤掉空内容和过大的消息
        llm_messages = []
        for m in messages_data:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > 8000:
                content = content[:8000] + "\n[TRUNCATED for replay]"

            # 跳过没有内容的非 system 消息
            if not content and role != "system":
                continue

            llm_messages.append(
                LLMMessage(
                    role=role,
                    content=content,
                    name=m.get("name"),
                    tool_calls=m.get("tool_calls"),
                    tool_call_id=m.get("tool_call_id"),
                )
            )

        # 4. 发送到 LLM
        try:
            response = await provider.chat(
                messages=llm_messages,
                tools=tools_spec,
                temperature=0.2,
            )
            new_answer = response.content
            new_usage = response.usage
        except Exception as e:
            logger.exception("Replay LLM call failed for trace %s", trace_id)
            return jsonify(
                {"code": 500, "message": f"LLM call failed: {e}"}
            ), 500
        finally:
            await provider.close()

        # 5. 获取原始运行结果
        original = await deps.mysql.async_fetch_one(
            "SELECT * FROM agent_run_summaries WHERE trace_id=%s",
            params=(trace_id,),
        )

        original_answer = None
        original_usage = None
        if original:
            original_answer = original.get("final_answer")
            original_usage = original.get("token_usage")
            if isinstance(original_usage, str):
                original_usage = json.loads(original_usage)

        return jsonify(
            {
                "code": 0,
                "data": {
                    "trace_id": trace_id,
                    "model": config.model,
                    "step": last_event["sequence"],
                    "prompt_message_count": len(llm_messages),
                    "original": {
                        "final_answer": original_answer,
                        "token_usage": original_usage,
                    },
                    "replay": {
                        "final_answer": new_answer,
                        "token_usage": {"prompt": new_usage.get("prompt_tokens", 0) if new_usage else 0, "completion": new_usage.get("completion_tokens", 0) if new_usage else 0, "total": new_usage.get("total_tokens", 0) if new_usage else 0} if new_usage else None,
                    },
                },
            }
        )

    return bp
