"""MCP Loader (OPT-15) — 连接 MCP server，映射 tool → Skill"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.agents.capabilities.skills import Skill, SkillType, RiskLevel
from src.core.agents.capabilities.skills.serializer import _build_json_schema

logger = logging.getLogger(__name__)


class MCPToolLoader:
    """MCP 工具加载器。

    连接 MCP server（stdio / SSE），发现 tools，包装为本系统 Skill 注册进 registry。

    支持两种传输：
    - stdio: 子进程通信
    - sse: HTTP SSE 长连接
    """

    def __init__(
        self,
        registry,
        default_risk_level: RiskLevel = RiskLevel.WRITE,
        timeout: float = 30.0,
    ):
        self._registry = registry
        self._default_risk = default_risk_level
        self._timeout = timeout

    async def load_from_server(
        self,
        server_name: str,
        transport: str = "stdio",
        command: Optional[List[str]] = None,
        url: Optional[str] = None,
    ) -> List[Skill]:
        """
        加载 MCP server 的所有 tool。

        Args:
            server_name: 服务器标识（用于命名空间）
            transport: "stdio" 或 "sse"
            command: stdio 模式下的子进程命令
            url: SSE 模式下的服务器 URL

        Returns:
            注册的 Skill 列表
        """
        tools = await self._discover_tools(server_name, transport, command, url)
        skills = []

        for tool in tools:
            skill = self._tool_to_skill(server_name, tool)
            if skill:
                self._registry.register(skill)
                skills.append(skill)
                logger.info(
                    "MCP tool loaded: %s/%s → %s",
                    server_name, tool.get("name"), skill.name,
                )

        return skills

    async def _discover_tools(
        self,
        server_name: str,
        transport: str,
        command: Optional[List[str]],
        url: Optional[str],
    ) -> List[Dict[str, Any]]:
        """通过 MCP 协议发现工具列表"""
        if transport == "stdio":
            return await self._discover_stdio(server_name, command)
        elif transport == "sse":
            return await self._discover_sse(server_name, url)
        raise ValueError(f"Unsupported MCP transport: {transport}")

    async def _discover_stdio(
        self, server_name: str, command: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """通过 MCP stdio 子进程发现工具"""
        if not command:
            logger.warning("MCP stdio transport requires command, skipping server %s", server_name)
            return []
        import asyncio
        import json as _json

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # MCP 握手: initialize → tools/list
            init_req = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            tools_req = _json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

            if proc.stdin:
                proc.stdin.write((init_req + "\n").encode())
                proc.stdin.write((tools_req + "\n").encode())
                await proc.stdin.drain()

            # 读取响应
            response_text = ""
            if proc.stdout:
                async for line in proc.stdout:
                    response_text += line.decode()
                    if "tools/list" in response_text and "result" in response_text:
                        break

            proc.terminate()
            await proc.wait()

            data = self._parse_mcp_response(response_text)
            return data.get("tools", [])
        except Exception:
            logger.exception("MCP stdio discovery failed for server %s", server_name)
            return []

    async def _discover_sse(
        self, server_name: str, url: Optional[str]
    ) -> List[Dict[str, Any]]:
        """通过 MCP SSE 端点发现工具"""
        if not url:
            logger.warning("MCP SSE transport requires URL, skipping server %s", server_name)
            return []
        try:
            import aiohttp
            import json as _json

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{url}/tools/list",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    data = await resp.json()
                    return data.get("result", {}).get("tools", [])
        except ImportError:
            logger.warning("aiohttp not available for MCP SSE transport")
            return []
        except Exception:
            logger.exception("MCP SSE discovery failed for server %s", server_name)
            return []

    def _tool_to_skill(self, server_name: str, tool: Dict[str, Any]) -> Optional[Skill]:
        """MCP tool → 本系统 Skill"""
        name = tool.get("name")
        if not name:
            return None

        description = tool.get("description", f"MCP tool from {server_name}")
        input_schema = tool.get("inputSchema", {})

        # 映射参数
        parameters = {}
        props = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))
        for prop_name, prop_info in props.items():
            parameters[prop_name] = {
                "type": prop_info.get("type", "string"),
                "description": prop_info.get("description", ""),
                "required": prop_name in required,
            }

        # handler：远程调用 MCP tool
        async def mcp_handler(ctx, **params):
            logger.debug("MCP call: %s/%s(%s)", server_name, name, params)
            return f"[MCP:{server_name}/{name}] called with {params} — stub: real MCP client integration needed"

        skill_id = f"mcp_{server_name}_{name}"
        return Skill(
            skill_id=skill_id,
            name=f"mcp_{server_name}_{name}",
            description=f"[MCP:{server_name}] {description}",
            skill_type=SkillType.EXECUTABLE,
            handler=mcp_handler,
            parameters=parameters,
            risk_level=self._default_risk,
            domain="mcp",
            tags=[server_name, "mcp"],
        )

    @staticmethod
    def _parse_mcp_response(text: str) -> Dict[str, Any]:
        """解析 MCP JSON-RPC 响应（从多行中提取最后一个完整 JSON 对象）"""
        import json as _json

        # 尝试解析每一行
        for line in reversed(text.strip().split("\n")):
            try:
                data = _json.loads(line)
                if "result" in data:
                    return data["result"]
            except _json.JSONDecodeError:
                continue
        return {}


__all__ = ["MCPToolLoader"]
