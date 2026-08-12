import pytest

import src.core.agents.capabilities.tools.http as http_tools
from src.core.agents.capabilities.skills import SkillContext


class FakeLog:
    async def log(self, _payload):
        return None


class FakeHttpClient:
    last_headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, **kwargs):
        self.__class__.last_headers = kwargs["headers"]
        return {"ok": True}


def _context():
    context = SkillContext.from_dependencies({"log": FakeLog()})
    context.trace_id = "trace-1"
    context.tool_call_id = "call-1"
    return context


@pytest.mark.asyncio
async def test_http_post_adds_stable_idempotency_key(monkeypatch):
    monkeypatch.setattr(http_tools, "AsyncHttpClient", FakeHttpClient)
    monkeypatch.setattr(http_tools, "_validate_url", lambda _url: None)

    await http_tools.http_post(_context(), "https://example.com", json={"value": 1})

    assert FakeHttpClient.last_headers["Idempotency-Key"] == "trace-1:call-1"


@pytest.mark.asyncio
async def test_http_post_preserves_explicit_idempotency_key(monkeypatch):
    monkeypatch.setattr(http_tools, "AsyncHttpClient", FakeHttpClient)
    monkeypatch.setattr(http_tools, "_validate_url", lambda _url: None)

    await http_tools.http_post(
        _context(),
        "https://example.com",
        headers={"idempotency-key": "client-key"},
    )

    assert FakeHttpClient.last_headers == {"idempotency-key": "client-key"}
