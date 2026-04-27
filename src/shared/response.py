class Response:
    @classmethod
    def success_response(cls, data):
        return {"code": 0, "status": "success", "data": data}

    @classmethod
    def error_response(cls, error_code, error_message):
        return {"code": error_code, "status": "error", "message": error_message}


class TaskScheduleResponse:
    @classmethod
    async def fail_response(cls, error_code, error_message):
        return {"code": error_code, "status": "error", "message": error_message}

    @classmethod
    async def success_response(cls, task_name, data):
        return {
            "code": 0,
            "status": "task execute successfully",
            "data": data,
            "task_name": task_name,
        }
