"""
HTTP Tools - HTTP 客户端工具

封装 AsyncHttpClient 为 Agent 可调用的技能
"""

from typing import Any, Dict, Optional

from src.core.agents.skills import skill, SkillContext
from src.infra.shared import AsyncHttpClient


@skill(
    name="http_get",
    description="发送 HTTP GET 请求，获取数据",
    dependencies=["log"],
    parameters={
        "url": {
            "type": "string",
            "description": "请求 URL",
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
    await ctx.log.log({
        "event": "http_get",
        "url": url,
        "params": params,
    })

    async with AsyncHttpClient() as client:
        response = await client.get(url=url, params=params, headers=headers)
        return response


@skill(
    name="http_post",
    description="发送 HTTP POST 请求，提交数据",
    dependencies=["log"],
    parameters={
        "url": {
            "type": "string",
            "description": "请求 URL",
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
    await ctx.log.log({
        "event": "http_post",
        "url": url,
        "has_json": json is not None,
        "has_data": data is not None,
    })

    async with AsyncHttpClient() as client:
        response = await client.post(
            url=url, json=json, data=data, headers=headers
        )
        return response
