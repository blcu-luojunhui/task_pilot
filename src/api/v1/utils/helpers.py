from __future__ import annotations

from typing import Any, Dict, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError
from quart import request

from src.infra.shared import ErrorCode

T = TypeVar("T", bound=BaseModel)


async def parse_json(model: Type[T]) -> Tuple[T, Dict[str, Any]]:
    """
    解析 JSON 请求体并用 Pydantic 校验。

    Returns:
        (obj, raw_dict) 方便向下兼容。
    """
    raw = await request.get_json()
    raw = raw or {}
    obj = model.model_validate(raw)
    return obj, raw


def validation_error_response(e: ValidationError) -> Tuple[Dict[str, Any], int]:
    return {"code": ErrorCode.BAD_REQUEST, "message": "invalid request body", "errors": e.errors()}, 400
