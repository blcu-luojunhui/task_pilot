"""
DeepSeek chat planner (DEPRECATED).

This module is deprecated. Use ``DeepSeekProvider`` from
``src.core.agents.capabilities.llm.providers.deepseek`` instead.

DeepSeek exposes an OpenAI-compatible chat completions API, so this planner
serializes registered skills as tools and normalizes returned tool calls into
the internal AgentLoopRunner message shape.
"""

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from src.core.agents.state.protocol import ToolCall, assistant_message, get_tool_calls
from src.infra.streaming.agents import get_stream_context
from src.core.agents.capabilities.skills import SkillRegistry


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs into os.environ if they are not set."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class DeepSeekSettings:
    """Runtime settings for DeepSeek API calls."""

    api_key: str
    model: str = DEFAULT_DEEPSEEK_MODEL
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    temperature: float = 0.2
    max_tokens: int = 1200
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "DeepSeekSettings":
        load_dotenv(env_file)
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required. Put it in .env or export it.")

        return cls(
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL),
            base_url=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "1200")),
            timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        )


@dataclass
class DeepSeekPlanner:
    """Planner callable used by AgentLoopRunner."""

    goal: str
    registry: SkillRegistry
    settings: DeepSeekSettings
    system_prompt: Optional[str] = None
    force_first_tool_name: Optional[str] = None
    disable_tools_after_first_tool: bool = True

    async def __call__(
        self,
        messages: List[Dict[str, Any]],
        step: int,
    ) -> Dict[str, Any]:
        warnings.warn(
            "DeepSeekPlanner is deprecated, use DeepSeekProvider instead",
            DeprecationWarning,
            stacklevel=2,
        )
        forced_tool_done = self._has_tool_result(messages, self.force_first_tool_name)
        payload = {
            "model": self.settings.model,
            "messages": self._to_deepseek_messages(messages),
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }

        tools = []
        if not (self.disable_tools_after_first_tool and forced_tool_done):
            tools = self._tool_specs()
        if tools:
            payload["tools"] = tools
            if self.force_first_tool_name and not forced_tool_done:
                payload["tool_choice"] = {
                    "type": "function",
                    "function": {"name": self.force_first_tool_name},
                }
            else:
                payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=self.settings.timeout_seconds)

        stream_ctx = get_stream_context()
        use_streaming = stream_ctx and stream_ctx.sink

        if use_streaming:
            payload["stream"] = True

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self.settings.base_url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise RuntimeError(f"DeepSeek API error {response.status}: {body}")

                if use_streaming:
                    message = await self._handle_streaming_response(response, stream_ctx.sink)
                else:
                    body = await response.text()
                    data = json.loads(body)
                    message = data["choices"][0]["message"]

        return self._from_deepseek_message(message)

    def _tool_specs(self) -> List[Dict[str, Any]]:
        return [{"type": "function", "function": spec} for spec in self.registry.to_tool_specs()]

    def _has_tool_result(
        self,
        messages: List[Dict[str, Any]],
        tool_name: Optional[str],
    ) -> bool:
        if not tool_name:
            return False
        return any(
            message.get("role") == "tool" and message.get("name") == tool_name
            for message in messages
        )

    def _to_deepseek_messages(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []

        if self.system_prompt:
            output.append({"role": "system", "content": self.system_prompt})

        for message in messages:
            role = message.get("role")
            if role == "assistant":
                output.append(self._assistant_to_deepseek(message))
            elif role == "tool":
                output.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id", ""),
                        "content": str(message.get("content", "")),
                    }
                )
            elif role in {"system", "user"}:
                output.append(
                    {
                        "role": role,
                        "content": str(message.get("content", "")),
                    }
                )

        if not any(message.get("role") == "user" for message in output):
            output.append({"role": "user", "content": self.goal})

        return output

    def _assistant_to_deepseek(self, message: Dict[str, Any]) -> Dict[str, Any]:
        output = {
            "role": "assistant",
            "content": message.get("content"),
        }

        tool_calls = get_tool_calls(message)
        if tool_calls:
            output["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": self._arguments_to_json(call.arguments),
                    },
                }
                for call in tool_calls
            ]

        return output

    def _from_deepseek_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=call.get("id", ""),
                    name=function.get("name", ""),
                    arguments=function.get("arguments") or {},
                )
            )

        return assistant_message(
            content=message.get("content"),
            tool_calls=tool_calls,
        )

    def _arguments_to_json(self, arguments: Any) -> str:
        if isinstance(arguments, str):
            return arguments
        return json.dumps(arguments, ensure_ascii=False)

    async def _handle_streaming_response(
        self,
        response: aiohttp.ClientResponse,
        sink: Any,
    ) -> Dict[str, Any]:
        content_parts = []
        tool_calls_by_index: Dict[int, Dict[str, Any]] = {}

        async for line in response.content:
            line_text = line.decode("utf-8").strip()
            if not line_text or line_text.startswith(":"):
                continue
            if not line_text.startswith("data: "):
                continue

            data_text = line_text[6:]
            if data_text == "[DONE]":
                break

            try:
                chunk = json.loads(data_text)
            except json.JSONDecodeError:
                continue

            delta = chunk.get("choices", [{}])[0].get("delta", {})

            if "content" in delta and delta["content"]:
                content_parts.append(delta["content"])
                await self._emit_delta(sink, "text", {"text": delta["content"]})

            if "tool_calls" in delta:
                for tc_delta in delta["tool_calls"]:
                    index = tc_delta.get("index", 0)
                    if index not in tool_calls_by_index:
                        tool_calls_by_index[index] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }

                    if "id" in tc_delta:
                        tool_calls_by_index[index]["id"] = tc_delta["id"]

                    if "function" in tc_delta:
                        func_delta = tc_delta["function"]
                        if "name" in func_delta:
                            tool_calls_by_index[index]["function"]["name"] += func_delta["name"]
                            await self._emit_delta(
                                sink,
                                "tool_call_name",
                                {
                                    "tool_call_index": index,
                                    "tool_call_id": tool_calls_by_index[index]["id"],
                                    "tool_name": tool_calls_by_index[index]["function"]["name"],
                                },
                            )
                        if "arguments" in func_delta:
                            tool_calls_by_index[index]["function"]["arguments"] += func_delta[
                                "arguments"
                            ]
                            await self._emit_delta(
                                sink,
                                "tool_call_arguments",
                                {
                                    "tool_call_index": index,
                                    "tool_call_id": tool_calls_by_index[index]["id"],
                                    "arguments_fragment": func_delta["arguments"],
                                },
                            )

        final_message = {
            "role": "assistant",
            "content": "".join(content_parts) or None,
        }
        if tool_calls_by_index:
            final_message["tool_calls"] = [
                tool_calls_by_index[i] for i in sorted(tool_calls_by_index.keys())
            ]

        return final_message

    async def _emit_delta(self, sink: Any, delta_kind: str, data: Dict[str, Any]) -> None:
        if sink is None:
            return
        event = {"delta_kind": delta_kind, **data}
        if callable(sink):
            result = sink(event)
            if hasattr(result, "__await__"):
                await result


__all__ = ["DeepSeekPlanner", "DeepSeekSettings", "load_dotenv"]
