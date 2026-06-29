"""
Utility Tools - 通用工具函数

封装常用工具为 Agent 可调用的技能
"""

import os
from datetime import datetime
from typing import List
from pathlib import Path

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
        "date_format": {
            "type": "string",
            "description": "时间格式字符串（默认 %Y-%m-%d %H:%M:%S）",
            "default": "%Y-%m-%d %H:%M:%S",
        },
    },
)
async def util_timestamp_to_str(
    ctx: SkillContext, timestamp: int, date_format: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """时间戳转字符串"""
    return timestamp_to_str(timestamp, date_format)


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
async def util_batch_split(ctx: SkillContext, data: List, batch_size: int) -> List[List]:
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


@skill(
    name="read_file",
    description="读取指定路径的文件内容，返回带行号的文本。支持 offset/limit 分页读取大文件。",
    dependencies=[],
    risk_level="read",
    parameters={
        "file_path": {
            "type": "string",
            "description": "文件路径（相对或绝对路径）",
            "required": True,
        },
        "offset": {
            "type": "integer",
            "description": "从第几行开始读取（1-based，默认 1）",
            "default": 1,
        },
        "limit": {
            "type": "integer",
            "description": "最多读取行数（默认 2000，最大 5000）",
            "default": 2000,
        },
    },
)
async def read_file(
    ctx: SkillContext, file_path: str, offset: int = 1, limit: int = 2000
) -> str:
    path = Path(file_path).resolve()
    limit = min(limit, 5000)

    # 安全校验：使用 realpath 后再判断
    real = Path(os.path.realpath(path))
    real_str = str(real)

    # 项目根目录白名单（仅允许读取项目目录下的文件）
    allowed_roots = [
        os.path.realpath(os.getcwd()),
    ]
    is_allowed = any(
        os.path.commonpath([real_str, root]) == root for root in allowed_roots
    )
    if not is_allowed:
        raise PermissionError(
            f"read_file denied: {real_str} is outside allowed directories"
        )

    # 禁止读取系统关键路径
    blocked_prefixes = (
        "/etc/", "/private/etc/",
        "/sys/", "/proc/", "/dev/",
        "/boot/", "/usr/", "/bin/", "/sbin/",
        "/var/", "/private/var/",
        "C:\\Windows\\",
    )
    for prefix in blocked_prefixes:
        if real_str.startswith(prefix):
            raise PermissionError(
                f"read_file denied: {real_str} is in a protected location"
            )

    # 检查读取敏感用户路径
    home = str(Path.home())
    sensitive_home_paths = (
        f"{home}/.ssh", f"{home}/.aws", f"{home}/.config",
        f"{home}/.gnupg", f"{home}/.kube", f"{home}/.docker",
        f"{home}/.npmrc", f"{home}/.bash_history", f"{home}/.zsh_history",
    )
    for sp in sensitive_home_paths:
        if real_str.startswith(sp):
            raise PermissionError(f"read_file denied: {sp} is protected")

    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not path.is_file():
        raise ValueError(f"路径不是文件: {path}")

    # 文件大小限制：最大 10 MB
    file_size = path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        raise ValueError(
            f"read_file denied: file size ({file_size} bytes) exceeds 10 MB limit"
        )

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 尝试以二进制读取，返回十六进制摘要
        raw = path.read_bytes()
        preview = raw[:200]
        return (
            f"[二进制文件] {path}\n"
            f"大小: {len(raw)} bytes\n"
            f"前 200 字节 (hex): {preview.hex()}"
        )

    lines = text.split("\n")
    total_lines = len(lines)

    # offset 1-based 转 0-based index
    start_idx = max(0, offset - 1)
    end_idx = min(start_idx + limit, total_lines)

    if start_idx >= total_lines:
        return f"[空范围] offset={offset} 超出文件总行数 {total_lines}"

    selected = lines[start_idx:end_idx]
    formatted_lines = []
    for i, line in enumerate(selected, start=start_idx + 1):
        formatted_lines.append(f"{i}\t{line}")

    header = (
        f"# {path}  (行 {start_idx + 1}-{end_idx}, 共 {total_lines} 行, "
        f"{file_size} bytes)\n"
    )
    return header + "\n".join(formatted_lines)


@skill(
    name="write_file",
    description="将内容写入指定路径的文件。如果文件已存在会覆盖，目录不存在会自动创建。",
    dependencies=[],
    risk_level="write",
    parameters={
        "file_path": {
            "type": "string",
            "description": "文件路径（相对或绝对路径）",
            "required": True,
        },
        "content": {
            "type": "string",
            "description": "要写入的文件内容",
            "required": True,
        },
    },
)
async def write_file(ctx: SkillContext, file_path: str, content: str) -> str:
    path = Path(file_path).resolve()

    # 大小限制
    if len(content) > 10 * 1024 * 1024:  # 10 MB
        raise ValueError("write_file denied: content exceeds 10 MB limit")

    # 安全校验：使用 realpath 后再判断
    real = Path(os.path.realpath(path))
    real_str = str(real)

    # 项目根目录白名单（仅允许在项目目录下写入）
    allowed_roots = [
        os.path.realpath(os.getcwd()),
    ]
    is_allowed = any(
        os.path.commonpath([real_str, root]) == root for root in allowed_roots
    )
    if not is_allowed:
        raise PermissionError(f"write_file denied: {real_str} is outside allowed directories")

    # 禁止写入系统关键路径
    blocked_prefixes = (
        "/etc/", "/private/etc/",
        "/sys/", "/proc/", "/dev/",
        "/boot/", "/usr/", "/bin/", "/sbin/",
        "/var/", "/private/var/",
        "C:\\Windows\\",
    )
    for prefix in blocked_prefixes:
        if real_str.startswith(prefix):
            raise PermissionError(f"write_file denied: {real_str} is in a protected location")

    # 检查写入 ~/.ssh, ~/.aws 等敏感用户路径
    home = str(Path.home())
    sensitive_home_paths = (
        f"{home}/.ssh", f"{home}/.aws", f"{home}/.config",
        f"{home}/.gnupg", f"{home}/.kube", f"{home}/.docker",
        f"{home}/.npmrc", f"{home}/.bash_history", f"{home}/.zsh_history",
    )
    for sp in sensitive_home_paths:
        if real_str.startswith(sp):
            raise PermissionError(f"write_file denied: {sp} is protected")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"文件已写入: {path} ({len(content)} 字符)"
