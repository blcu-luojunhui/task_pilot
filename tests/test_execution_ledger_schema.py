import pytest

from src.core.agents.execution import ensure_tool_execution_ledger
from src.core.agents.execution.ledger import CREATE_TOOL_EXECUTION_LEDGER_SQL


class RecordingDatabase:
    def __init__(self):
        self.calls = []

    async def async_save(self, query, params=None):
        self.calls.append((query, params))
        return 0


@pytest.mark.asyncio
async def test_ledger_schema_is_additive_and_idempotent():
    database = RecordingDatabase()

    await ensure_tool_execution_ledger(database)

    assert database.calls == [(CREATE_TOOL_EXECUTION_LEDGER_SQL, None)]
    assert "CREATE TABLE IF NOT EXISTS agent_tool_executions" in database.calls[0][0]
    assert "UNIQUE INDEX uk_trace_tool_call" in database.calls[0][0]
