"""
JSON 列归一化工具

aiomysql DictCursor 不会自动反序列化 JSON 列，需要在 API 边界手动处理。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


def decode_json_columns(
    rows: Iterable[Mapping[str, Any]],
    columns: Iterable[str],
    *,
    default: Any = None,
) -> list[dict]:
    """对每行做指定列的 JSON 反序列化。dict 透传、字符串 json.loads、None/空字符串给 default。"""
    cols = tuple(columns)
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        for col in cols:
            item[col] = _decode(item.get(col), default)
        result.append(item)
    return result


def decode_json_row(
    row: Mapping[str, Any] | None,
    columns: Iterable[str],
    *,
    default: Any = None,
) -> dict | None:
    if row is None:
        return None
    return decode_json_columns([row], columns, default=default)[0]


def _decode(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


__all__ = ["decode_json_columns", "decode_json_row"]
