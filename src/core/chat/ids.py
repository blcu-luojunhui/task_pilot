"""Chat 领域 ID 生成。和 trace_id 风格保持一致，便于跨表关联与日志检索。"""
from __future__ import annotations

import random
import string
from datetime import datetime


def generate_conversation_id() -> str:
    """生成会话 ID。

    格式 ``Conv-YYYYmmddHHMMSS-<16 位 hex>``，与 ``Task-`` / ``Agent-`` 保持一致。
    """
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
    return f"Conv-{datetime.now().strftime('%Y%m%d%H%M%S')}-{suffix}"


__all__ = ["generate_conversation_id"]
