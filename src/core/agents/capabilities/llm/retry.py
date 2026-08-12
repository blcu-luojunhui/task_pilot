"""Retry policy for transient LLM provider failures."""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Optional, TypeVar

import aiohttp

from src.core.agents.exceptions import LLMProviderError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class LLMRetryPolicy:
    """Bounded exponential backoff for retryable provider errors."""

    max_retries: int = 2
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry limits and delays must be >= 0")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def is_retryable(self, error: BaseException) -> bool:
        return isinstance(error, (LLMRateLimitError, LLMTimeoutError, aiohttp.ClientError)) or (
            isinstance(error, LLMProviderError) and error.status_code >= 500
        )

    def delay_for(self, error: BaseException, retry_number: int) -> float:
        base = error.retry_after if isinstance(error, LLMRateLimitError) and error.retry_after > 0 else self.base_delay_seconds * (2 ** max(retry_number - 1, 0))
        delay = min(base, self.max_delay_seconds)
        return delay + (random.uniform(0, delay * self.jitter_ratio) if delay else 0)

    async def call(self, operation: Callable[[], Awaitable[T]], *, on_retry: Optional[Callable[[dict[str, Any]], Any]] = None) -> T:
        for attempt in range(1, self.max_retries + 2):
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if attempt > self.max_retries or not self.is_retryable(error):
                    raise
                delay = self.delay_for(error, attempt)
                detail = {
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "max_attempts": self.max_retries + 1,
                    "delay_seconds": round(delay, 3),
                    "error_type": type(error).__name__,
                }
                logger.warning("Retrying LLM call: %s", detail)
                if on_retry:
                    result = on_retry(detail)
                    if inspect.isawaitable(result):
                        await result
                if delay:
                    await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def iterate(
        self,
        operation: Callable[[], AsyncIterator[T]],
        *,
        on_retry: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> AsyncIterator[T]:
        """Retry a stream only before its first item to prevent duplicate output."""
        for attempt in range(1, self.max_retries + 2):
            emitted = False
            try:
                async for item in operation():
                    emitted = True
                    yield item
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if emitted or attempt > self.max_retries or not self.is_retryable(error):
                    raise
                delay = self.delay_for(error, attempt)
                detail = {
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "max_attempts": self.max_retries + 1,
                    "delay_seconds": round(delay, 3),
                    "error_type": type(error).__name__,
                }
                if on_retry:
                    result = on_retry(detail)
                    if inspect.isawaitable(result):
                        await result
                if delay:
                    await asyncio.sleep(delay)


__all__ = ["LLMRetryPolicy"]
