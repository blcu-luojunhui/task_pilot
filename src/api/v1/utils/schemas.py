from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseRequest(BaseModel):
    """所有请求模型基类：默认允许额外字段，避免破坏兼容性。"""

    model_config = ConfigDict(extra="allow")


class RunTaskRequest(BaseRequest):
    task_name: str = Field(..., min_length=1)
    date_string: Optional[str] = None


class CancelTaskRequest(BaseRequest):
    trace_id: str = Field(..., min_length=1)
