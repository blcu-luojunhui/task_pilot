from enum import IntEnum


class ErrorCode(IntEnum):
    """统一错误码定义"""

    # 成功
    SUCCESS = 0

    # 4xxx: 客户端错误
    BAD_REQUEST = 4000
    UNKNOWN_TASK = 4001
    VALIDATION_ERROR = 4003
    RATE_LIMITED = 4029

    # 5xxx: 服务端错误
    INTERNAL_ERROR = 5000
    TASK_ALREADY_PROCESSING = 5001
    SERVICE_SHUTTING_DOWN = 5003
    CONCURRENCY_LIMIT = 5005


__all__ = ["ErrorCode"]
