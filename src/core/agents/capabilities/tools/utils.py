"""
Utility Tools - 通用工具函数

封装常用工具为 Agent 可调用的技能
"""

from datetime import datetime
from typing import List

from src.core.agents.capabilities.skills import skill, SkillContext
from src.infra.shared.tools import (
    str_to_md5,
    timestamp_to_str,
    generate_task_trace_id,
)


@skill(
    name="util_md5",
    description="计算字符串的 MD5 哈希值",
    dependencies=[],
    risk_level="read",
    parameters={
        "text": {
            "type": "string",
            "description": "要计算哈希的字符串",
            "required": True,
        },
    },
)
async def util_md5(ctx: SkillContext, text: str) -> str:
    """计算 MD5 哈希"""
    return str_to_md5(text)


@skill(
    name="util_timestamp_to_str",
    description="将 Unix 时间戳转换为格式化字符串",
    dependencies=[],
    risk_level="read",
    parameters={
        "timestamp": {
            "type": "number",
            "description": "Unix 时间戳（秒）",
            "required": True,
        },
        "format": {
            "type": "string",
            "description": "时间格式字符串（默认 %Y-%m-%d %H:%M:%S）",
            "default": "%Y-%m-%d %H:%M:%S",
        },
    },
)
async def util_timestamp_to_str(
    ctx: SkillContext, timestamp: int, format: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """时间戳转字符串"""
    return timestamp_to_str(timestamp, format)


@skill(
    name="util_generate_trace_id",
    description="生成唯一的任务追踪 ID",
    dependencies=[],
    risk_level="read",
    parameters={},
)
async def util_generate_trace_id(ctx: SkillContext) -> str:
    """生成追踪 ID"""
    return generate_task_trace_id()


@skill(
    name="util_batch_split",
    description="将列表分批处理",
    dependencies=[],
    risk_level="read",
    parameters={
        "data": {
            "type": "array",
            "description": "要分批的数据列表",
            "required": True,
        },
        "batch_size": {
            "type": "integer",
            "description": "每批大小",
            "required": True,
        },
    },
)
async def util_batch_split(
    ctx: SkillContext, data: List, batch_size: int
) -> List[List]:
    """分批处理数据"""
    from src.infra.shared.tools import yield_batch

    batches = list(yield_batch(data, batch_size))
    return batches


@skill(
    name="util_current_time",
    description="获取当前时间（ISO 格式字符串）",
    dependencies=[],
    risk_level="read",
    parameters={},
)
async def util_current_time(ctx: SkillContext) -> str:
    """获取当前时间"""
    return datetime.now().isoformat()
