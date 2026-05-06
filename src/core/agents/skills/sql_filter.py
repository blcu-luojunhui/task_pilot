"""
SQL 安全过滤器

在数据库工具执行前校验 SQL 语句，拦截危险操作
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


# 默认禁止的 SQL 模式（针对 db_execute）
DEFAULT_BLOCKED_PATTERNS = [
    r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",
    r"\bTRUNCATE\s+TABLE\b",
    r"\bALTER\s+(TABLE|DATABASE)\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bCREATE\s+DATABASE\b",
]


@dataclass
class SQLFilter:
    """SQL 语句安全过滤器"""

    # 禁止的 SQL 模式（正则表达式）
    blocked_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_BLOCKED_PATTERNS))
    # 是否只允许 SELECT（用于 db_query/db_query_one）
    allow_only_select: bool = False
    # 是否禁止多语句（分号分隔）
    block_multi_statement: bool = True

    def validate(self, sql: str, tool_name: str = "") -> Optional[str]:
        """
        校验 SQL 语句安全性。

        Returns:
            None if SQL is safe, error message string if blocked.
        """
        if not sql or not sql.strip():
            return "Empty SQL statement"

        normalized = self._strip_comments(sql).strip()

        # 多语句检查
        if self.block_multi_statement and self._has_multiple_statements(normalized):
            return f"Multiple SQL statements are not allowed (tool: {tool_name})"

        # SELECT-only 检查
        if self.allow_only_select:
            if not normalized.upper().startswith("SELECT"):
                return (
                    f"Only SELECT statements are allowed for tool '{tool_name}', "
                    f"got: {normalized[:50]}..."
                )

        # 危险模式检查
        for pattern in self.blocked_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return (
                    f"SQL statement blocked by security filter "
                    f"(matched pattern: {pattern}, tool: {tool_name})"
                )

        return None

    def _strip_comments(self, sql: str) -> str:
        """移除 SQL 注释，防止通过注释隐藏危险语句"""
        # 移除单行注释 (-- ...)
        sql = re.sub(r"--[^\n]*", "", sql)
        # 移除多行注释 (/* ... */)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        return sql

    def _has_multiple_statements(self, sql: str) -> bool:
        """检查是否包含多条语句（忽略字符串内的分号）"""
        # 简单策略：移除引号内容后检查分号
        cleaned = re.sub(r"'[^']*'", "", sql)
        cleaned = re.sub(r'"[^"]*"', "", cleaned)
        # 去掉末尾的分号后检查是否还有分号
        cleaned = cleaned.rstrip().rstrip(";")
        return ";" in cleaned


# 预配置的过滤器实例
QUERY_FILTER = SQLFilter(allow_only_select=True)
EXECUTE_FILTER = SQLFilter(allow_only_select=False)


__all__ = ["SQLFilter", "QUERY_FILTER", "EXECUTE_FILTER"]
