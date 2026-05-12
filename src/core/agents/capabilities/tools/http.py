"""
HTTP Tools - HTTP 客户端工具

封装 AsyncHttpClient 为 Agent 可调用的技能
"""

import ipaddress
import socket
from urllib.parse import urlparse
from typing import Any, Dict, Optional

from src.core.agents.capabilities.skills import skill, SkillContext
from src.infra.shared import AsyncHttpClient

# 默认允许的 URL scheme
_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_ip(hostname: str) -> bool:
    """通过 DNS 解析后判断 IP 是否为内网/环回/链路本地地址"""
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # 非 IP 字面量，尝试 DNS 解析
        try:
            resolved = socket.gethostbyname(hostname)
        except socket.gaierror:
            return True  # 无法解析则拒绝
        addr = ipaddress.ip_address(resolved)

    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_unspecified


def _validate_url(url: str) -> None:
    """校验 URL，防止 SSRF（含 DNS rebinding / IPv6 私网 / 数字 host 防护）"""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise PermissionError(f"URL scheme '{parsed.scheme}' not allowed, only http/https")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError(f"Invalid URL: no hostname in '{url}'")

    # 移除 IPv6 地址的方括号
    raw_host = hostname.strip("[]")

    # 字符串层面的快速拒绝
    if raw_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise PermissionError(f"URL host '{hostname}' is blocked")

    # 使用 ipaddress 模块全面判断私网/环回/链路本地
    try:
        ip = ipaddress.ip_address(raw_host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise PermissionError(f"URL host '{hostname}' is in a reserved IP range")
    except ValueError:
        pass  # 非 IP 字面量，进一步通过 DNS 检查

    # DNS 解析检查（防 DNS rebinding / 域名指向内网）
    if _is_private_ip(raw_host):
        raise PermissionError(f"URL host '{hostname}' resolves to a private/reserved address")



@skill(
    name="http_get",
    description="发送 HTTP GET 请求，获取数据",
    dependencies=["log"],
    risk_level="read",
    parameters={
        "url": {
            "type": "string",
            "description": "请求 URL（仅限 http/https 公网地址）",
            "required": True,
        },
        "params": {
            "type": "object",
            "description": "URL 查询参数（dict）",
            "required": False,
        },
        "headers": {
            "type": "object",
            "description": "自定义 HTTP headers（dict）",
            "required": False,
        },
    },
)
async def http_get(
    ctx: SkillContext,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """发送 GET 请求"""
    _validate_url(url)
    await ctx.log.log(
        {
            "event": "http_get",
            "url": url,
            "params": params,
        }
    )

    async with AsyncHttpClient() as client:
        response = await client.get(url=url, params=params, headers=headers)
        return response


@skill(
    name="http_post",
    description="发送 HTTP POST 请求，提交数据",
    dependencies=["log"],
    risk_level="write",
    parameters={
        "url": {
            "type": "string",
            "description": "请求 URL（仅限 http/https 公网地址）",
            "required": True,
        },
        "json": {
            "type": "object",
            "description": "JSON 数据（dict）",
            "required": False,
        },
        "data": {
            "type": "object",
            "description": "表单数据（dict）",
            "required": False,
        },
        "headers": {
            "type": "object",
            "description": "自定义 HTTP headers（dict）",
            "required": False,
        },
    },
)
async def http_post(
    ctx: SkillContext,
    url: str,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    """发送 POST 请求"""
    _validate_url(url)
    await ctx.log.log(
        {
            "event": "http_post",
            "url": url,
            "has_json": json is not None,
            "has_data": data is not None,
        }
    )

    async with AsyncHttpClient() as client:
        response = await client.post(url=url, json=json, data=data, headers=headers)
        return response
