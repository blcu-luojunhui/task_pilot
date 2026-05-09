"""
HTTP Tools - HTTP 客户端工具

封装 AsyncHttpClient 为 Agent 可调用的技能
"""

from urllib.parse import urlparse
from typing import Any, Dict, Optional

from src.core.agents.capabilities.skills import skill, SkillContext
from src.infra.shared import AsyncHttpClient

# 默认允许的 URL scheme
_ALLOWED_SCHEMES = {"http", "https"}


def _validate_url(url: str) -> None:
    """校验 URL，防止 SSRF"""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise PermissionError(f"URL scheme '{parsed.scheme}' not allowed, only http/https")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError(f"Invalid URL: no hostname in '{url}'")
    # 禁止访问内网/保留地址
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]", "[0:0:0:0:0:0:0:0]"):
        raise PermissionError(f"URL host '{hostname}' is blocked")
    # RFC 1918 私有 IP: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
    if hostname.startswith("10.") or hostname.startswith("192.168."):
        raise PermissionError(f"URL host '{hostname}' is in private range")
    if hostname.startswith("172."):
        parts = hostname.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            second = int(parts[1])
            if 16 <= second <= 31:
                raise PermissionError(f"URL host '{hostname}' is in private range (172.16-31)")
    # 链路本地 169.254.0.0/16
    if hostname.startswith("169.254."):
        raise PermissionError(f"URL host '{hostname}' is in link-local range")


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
