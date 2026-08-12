import pytest

from src.core.agents.capabilities.skills import RiskLevel, Skill, SkillExecutor, SkillRegistry
from src.core.agents.engine.loop import Act
from src.core.agents.execution import (
    DBToolExecutionLedger,
    LedgerState,
    ToolExecutionLedgerError,
)
from src.core.agents.state import AgentLoopState, StopReason
from src.core.agents.state.protocol import ToolCall


class MemoryLedgerDatabase:
    def __init__(self):
        self.rows = {}
        self.available = True

    async def async_save(self, query, params=None):
        if not self.available:
            raise RuntimeError("database down")
        if query.startswith("INSERT IGNORE"):
            trace_id, call_id, tool_name, digest, account_id = params
            key = (trace_id, call_id, account_id)
            if key in self.rows:
                return 0
            self.rows[key] = {
                "tool_name": tool_name,
                "arguments_digest": digest,
                "status": "running",
                "result_content": None,
                "error_message": None,
            }
            return 1
        status, result, error, trace_id, call_id, account_id = params
        row = self.rows.get((trace_id, call_id, account_id))
        if not row or row["status"] != "running":
            return 0
        row.update(status=status, result_content=result, error_message=error)
        return 1

    async def async_fetch_one(self, _query, params=None):
        if not self.available:
            raise RuntimeError("database down")
        return self.rows.get(tuple(params))


@pytest.mark.asyncio
async def test_database_ledger_claim_complete_and_replay():
    database = MemoryLedgerDatabase()
    ledger = DBToolExecutionLedger(database, account_id=7)

    claimed = await ledger.claim("trace", "call", "write", {"value": 1})
    await ledger.complete("trace", "call", "saved")
    replayed = await ledger.claim("trace", "call", "write", {"value": 1})

    assert claimed.state == LedgerState.CLAIMED
    assert replayed.state == LedgerState.COMPLETED
    assert replayed.result_content == "saved"


@pytest.mark.asyncio
async def test_database_ledger_rejects_call_id_argument_drift():
    ledger = DBToolExecutionLedger(MemoryLedgerDatabase(), account_id=7)
    await ledger.claim("trace", "call", "write", {"value": 1})

    with pytest.raises(ToolExecutionLedgerError, match="reused"):
        await ledger.claim("trace", "call", "write", {"value": 2})


@pytest.mark.asyncio
async def test_database_ledger_reconciliation_is_idempotent_but_not_reversible():
    database = MemoryLedgerDatabase()
    ledger = DBToolExecutionLedger(database, account_id=7)
    await ledger.claim("trace", "call", "write", {"value": 1})

    await ledger.resolve(
        "trace",
        "call",
        decision="completed",
        result_content="verified",
    )
    await ledger.resolve(
        "trace",
        "call",
        decision="completed",
        result_content="verified",
    )

    with pytest.raises(ToolExecutionLedgerError, match="different outcome"):
        await ledger.resolve(
            "trace",
            "call",
            decision="failed",
            error_message="not written",
        )


def _actor(handler, ledger):
    registry = SkillRegistry(namespace="ledger")
    registry.register(
        Skill.executable(
            name="write_once",
            description="write",
            handler=handler,
            risk_level=RiskLevel.WRITE,
            parameters={"value": {"type": "integer", "required": True}},
        )
    )
    return Act(
        registry=registry,
        executor=SkillExecutor(),
        execution_ledger=ledger,
    )


@pytest.mark.asyncio
async def test_actor_replays_completed_write_without_second_side_effect():
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    ledger = DBToolExecutionLedger(MemoryLedgerDatabase())
    actor = _actor(handler, ledger)
    call = ToolCall("call-1", "write_once", {"value": 1})

    first = await actor.run(AgentLoopState(trace_id="trace"), [call])
    second = await actor.run(AgentLoopState(trace_id="trace"), [call])

    assert executed == [1]
    assert second[0]["content"] == first[0]["content"]


@pytest.mark.asyncio
async def test_actor_blocks_in_doubt_write_without_execution():
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    database = MemoryLedgerDatabase()
    ledger = DBToolExecutionLedger(database)
    await ledger.claim("trace", "call-1", "write_once", {"value": 1})
    actor = _actor(handler, ledger)
    state = AgentLoopState(trace_id="trace")

    result = await actor.run(state, [ToolCall("call-1", "write_once", {"value": 1})])

    assert executed == []
    assert state.stop_reason == StopReason.EXECUTION_IN_DOUBT
    assert state.pending_reconciliation["tool_call_id"] == "call-1"
    assert state.pending_reconciliation["arguments"] == {"value": 1}
    assert "execution_in_doubt" in result[0]["content"]


@pytest.mark.asyncio
async def test_actor_replays_known_failed_write_as_tool_error_without_reconciliation():
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    database = MemoryLedgerDatabase()
    ledger = DBToolExecutionLedger(database)
    await ledger.claim("trace", "call-1", "write_once", {"value": 1})
    await ledger.fail("trace", "call-1", "downstream rejected write")
    actor = _actor(handler, ledger)
    state = AgentLoopState(trace_id="trace")

    result = await actor.run(state, [ToolCall("call-1", "write_once", {"value": 1})])

    assert executed == []
    assert state.stop_reason is None
    assert state.pending_reconciliation is None
    assert "downstream rejected write" in result[0]["content"]


@pytest.mark.asyncio
async def test_actor_treats_unexpected_write_exception_as_in_doubt():
    async def handler(_ctx, value):
        raise RuntimeError(f"connection dropped after writing {value}")

    database = MemoryLedgerDatabase()
    actor = _actor(handler, DBToolExecutionLedger(database))
    state = AgentLoopState(trace_id="trace")

    await actor.run(state, [ToolCall("call-1", "write_once", {"value": 1})])

    assert state.stop_reason == StopReason.EXECUTION_IN_DOUBT
    assert state.pending_reconciliation["tool_call_id"] == "call-1"
    assert database.rows[("trace", "call-1", 0)]["status"] == "running"


@pytest.mark.asyncio
async def test_actor_fails_closed_when_ledger_is_unavailable():
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    database = MemoryLedgerDatabase()
    database.available = False
    actor = _actor(handler, DBToolExecutionLedger(database))

    result = await actor.run(
        AgentLoopState(trace_id="trace"),
        [ToolCall("call-1", "write_once", {"value": 1})],
    )

    assert executed == []
    assert "ledger is unavailable" in result[0]["content"]


@pytest.mark.asyncio
async def test_actor_rejects_invalid_write_before_ledger_claim():
    executed = []

    async def handler(_ctx, value):
        executed.append(value)
        return "saved"

    database = MemoryLedgerDatabase()
    actor = _actor(handler, DBToolExecutionLedger(database))

    result = await actor.run(
        AgentLoopState(trace_id="trace"),
        [ToolCall("call-1", "write_once", {"value": True})],
    )

    assert executed == []
    assert database.rows == {}
    assert "expected type 'integer'" in result[0]["content"]
