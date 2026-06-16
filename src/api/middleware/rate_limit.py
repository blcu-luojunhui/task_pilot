import time
from collections import defaultdict
from quart import Quart, request, jsonify

from src.infra.shared import ErrorCode


class RateLimitMiddleware:
    """
    基于 IP 的滑动窗口速率限制中间件。

    rate_limit_paths: 受默认限制的路径集合
    path_limits:     路径 → (max_requests, window_seconds) 差异化限制
                     不在 path_limits 中的路径使用默认值
    """

    def __init__(
        self,
        app: Quart,
        max_requests: int = 60,
        window_seconds: int = 60,
        rate_limit_paths: set = None,
        path_limits: dict = None,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.rate_limit_paths = rate_limit_paths or set()
        self.path_limits = path_limits or {}
        self._requests = defaultdict(list)

        app.before_request(self.before_request)

    @staticmethod
    def _get_client_ip() -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _cleanup(self, key: str, now: float, window: int):
        cutoff = now - window
        timestamps = self._requests[key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if not timestamps:
            del self._requests[key]

    def _get_limit_for_path(self, path: str) -> tuple[int, int] | None:
        """返回 (max_requests, window_seconds)，若非限流路径返回 None。"""
        if path in self.path_limits:
            return self.path_limits[path]
        if path in self.rate_limit_paths:
            return self.max_requests, self.window_seconds
        return None

    async def before_request(self):
        limit = self._get_limit_for_path(request.path)
        if limit is None:
            return None

        max_req, window = limit
        client_ip = self._get_client_ip()
        key = f"{client_ip}:{request.path}"
        now = time.time()

        self._cleanup(key, now, window)

        timestamps = self._requests[key]
        if len(timestamps) >= max_req:
            retry_after = int(window - (now - timestamps[0]))
            response = jsonify(
                {
                    "code": ErrorCode.RATE_LIMITED,
                    "message": "Too many requests, please try again later",
                }
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(max(1, retry_after))
            return response

        timestamps.append(now)
        return None


__all__ = ["RateLimitMiddleware"]
