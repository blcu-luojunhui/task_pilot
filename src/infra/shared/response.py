from .error_codes import ErrorCode


class ApiResponse:
    """统一 API 响应构造器"""

    @classmethod
    def success(cls, data=None, message: str = "success"):
        resp = {"code": ErrorCode.SUCCESS, "status": "success", "message": message}
        if data is not None:
            resp["data"] = data
        return resp

    @classmethod
    def error(cls, error_code: int, message: str, data=None):
        resp = {"code": error_code, "status": "error", "message": message}
        if data is not None:
            resp["data"] = data
        return resp

    @classmethod
    def task_started(cls, task_name: str, trace_id: str):
        return cls.success(
            data={
                "task_name": task_name,
                "trace_id": trace_id,
                "message": "Task started successfully",
            }
        )


# 向后兼容别名
class Response(ApiResponse):
    @classmethod
    def success_response(cls, data):
        return cls.success(data=data)

    @classmethod
    def error_response(cls, error_code, error_message):
        return cls.error(error_code, error_message)


class TaskScheduleResponse(ApiResponse):
    @classmethod
    def fail_response(cls, error_code: int, error_message: str):
        return cls.error(error_code, error_message)

    @classmethod
    def success_response(cls, task_name: str, data: dict):
        return cls.success(data=data)
