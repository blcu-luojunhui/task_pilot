import pytest

from src.core.agents.capabilities.llm.retry import LLMRetryPolicy
from src.core.agents.exceptions import LLMProviderError, LLMTimeoutError


@pytest.mark.asyncio
async def test_retries_transient_error_and_reports_attempt():
    calls = 0
    retries = []
    policy = LLMRetryPolicy(max_retries=2, base_delay_seconds=0, jitter_ratio=0)

    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise LLMTimeoutError("timeout")
        return "ok"

    result = await policy.call(operation, on_retry=retries.append)

    assert result == "ok"
    assert calls == 3
    assert [item["next_attempt"] for item in retries] == [2, 3]


@pytest.mark.asyncio
async def test_does_not_retry_non_transient_provider_error():
    calls = 0
    policy = LLMRetryPolicy(max_retries=3, base_delay_seconds=0)

    async def operation():
        nonlocal calls
        calls += 1
        raise LLMProviderError("test", "bad request", 400)

    with pytest.raises(LLMProviderError):
        await policy.call(operation)
    assert calls == 1


@pytest.mark.asyncio
async def test_stream_retries_before_first_token():
    calls = 0
    policy = LLMRetryPolicy(max_retries=1, base_delay_seconds=0, jitter_ratio=0)

    async def stream():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LLMTimeoutError("timeout")
        yield "done"

    output = [token async for token in policy.iterate(stream)]

    assert output == ["done"]
    assert calls == 2


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_emitting_token():
    calls = 0
    policy = LLMRetryPolicy(max_retries=2, base_delay_seconds=0)

    async def stream():
        nonlocal calls
        calls += 1
        yield "partial"
        raise LLMTimeoutError("timeout")

    output = []
    with pytest.raises(LLMTimeoutError):
        async for token in policy.iterate(stream):
            output.append(token)

    assert output == ["partial"]
    assert calls == 1
