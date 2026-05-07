import time
from collections import defaultdict
from quart import Quart, request, jsonify

from src.infra.shared import ErrorCode


class RateLimitMiddleware:
    """
    基于 IP 的滑动窗口速率限制中间件

    默认限制：每个 IP 每分钟最多 60 次请求
    可通过 rate_limit_paths 指定只对特定路径生效
    """

    def __init__(
        self,
        app: Quart,
        max_requests: int = 60,
        window_seconds: int = 60,
        rate_limit_paths: set = None,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.rate_limit_paths = rate_limit_paths
        self._requests = defaultdict(list)

        app.before_request(self.before_request)

    @staticmethod
    def _get_client_ip() -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def _cleanup(self, key: str, now: float):
        cutoff = now - self.window_seconds
        timestamps = self._requests[key]
        # 移除过期的时间戳
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if not timestamps:
            del self._requests[key]

    async def before_request(self):
        # 如果指定了路径，只对这些路径限流
        if self.rate_limit_paths and request.path not in self.rate_limit_paths:
            return None

        client_ip = self._get_client_ip()
        now = time.time()

        self._cleanup(client_ip, now)

        timestamps = self._requests[client_ip]
        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0]))
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
