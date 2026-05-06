"""
结构化工具输出

统一工具返回格式，让 LLM 更容易解析结果
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolOutput:
    """工具执行的结构化输出"""

    success: bool
    data: Any = None
    message: str = ""
    row_count: Optional[int] = None

    def serialize(self) -> str:
        """序列化为 LLM 可读的字符串"""
        parts = []

        if not self.success:
            parts.append(f"[ERROR] {self.message}")
            return "\n".join(parts)

        if self.message:
            parts.append(self.message)

        if self.row_count is not None:
            parts.append(f"({self.row_count} rows)")

        if self.data is not None:
            if isinstance(self.data, str):
                parts.append(self.data)
            else:
                parts.append(json.dumps(self.data, ensure_ascii=False, default=str))

        return "\n".join(parts) if parts else "OK"

    @classmethod
    def ok(cls, data: Any = None, message: str = "", row_count: Optional[int] = None) -> "ToolOutput":
        """创建成功输出"""
        return cls(success=True, data=data, message=message, row_count=row_count)

    @classmethod
    def error(cls, message: str) -> "ToolOutput":
        """创建错误输出"""
        return cls(success=False, message=message)


__all__ = ["ToolOutput"]
