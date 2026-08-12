"""Durable execution ledger for replay-safe tool calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional


CREATE_TOOL_EXECUTION_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS agent_tool_executions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id VARCHAR(128) NOT NULL,
    tool_call_id VARCHAR(128) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    arguments_digest CHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL,
    result_content LONGTEXT NULL,
    error_message TEXT NULL,
    account_id BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_trace_tool_call (trace_id, tool_call_id),
    INDEX idx_status_updated (status, updated_at),
    INDEX idx_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


class LedgerState(str, Enum):
    CLAIMED = "claimed"
    COMPLETED = "completed"
    FAILED = "failed"
    IN_DOUBT = "in_doubt"


@dataclass(frozen=True)
class LedgerClaim:
    state: LedgerState
    result_content: Optional[str] = None
    error_message: Optional[str] = None


class ToolExecutionLedgerError(RuntimeError):
    """Raised when the durable execution contract cannot be enforced."""


@dataclass
class DBToolExecutionLedger:
    """MySQL-backed at-most-once execution ledger."""

    database: Any
    account_id: int = 0

    @staticmethod
    def arguments_digest(arguments: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def claim(
        self,
        trace_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> LedgerClaim:
        digest = self.arguments_digest(arguments)
        try:
            inserted = await self.database.async_save(
                "INSERT IGNORE INTO agent_tool_executions "
                "(trace_id, tool_call_id, tool_name, arguments_digest, status, account_id) "
                "VALUES (%s, %s, %s, %s, 'running', %s)",
                (trace_id, tool_call_id, tool_name, digest, self.account_id),
            )
            if inserted:
                return LedgerClaim(LedgerState.CLAIMED)
            row = await self.database.async_fetch_one(
                "SELECT tool_name, arguments_digest, status, result_content, error_message "
                "FROM agent_tool_executions WHERE trace_id = %s AND tool_call_id = %s "
                "AND account_id = %s",
                params=(trace_id, tool_call_id, self.account_id),
            )
        except Exception as exc:
            raise ToolExecutionLedgerError("tool execution ledger is unavailable") from exc

        if not row:
            raise ToolExecutionLedgerError("tool execution claim disappeared")
        if row.get("tool_name") != tool_name or row.get("arguments_digest") != digest:
            raise ToolExecutionLedgerError(
                "tool_call_id was reused with different tool name or arguments"
            )
        status = row.get("status")
        if status == "completed":
            return LedgerClaim(LedgerState.COMPLETED, result_content=row.get("result_content"))
        if status == "failed":
            return LedgerClaim(LedgerState.FAILED, error_message=row.get("error_message"))
        return LedgerClaim(LedgerState.IN_DOUBT)

    async def complete(self, trace_id: str, tool_call_id: str, result_content: str) -> None:
        await self._finish(trace_id, tool_call_id, "completed", result_content, None)

    async def fail(self, trace_id: str, tool_call_id: str, error_message: str) -> None:
        await self._finish(trace_id, tool_call_id, "failed", None, error_message)

    async def resolve(
        self,
        trace_id: str,
        tool_call_id: str,
        *,
        decision: str,
        result_content: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Resolve an ambiguous running record after external verification."""
        if decision not in {"completed", "failed"}:
            raise ToolExecutionLedgerError(
                "reconciliation decision must be completed or failed"
            )
        if decision == "completed" and result_content is None:
            raise ToolExecutionLedgerError("completed reconciliation requires result_content")
        expected_error = (
            error_message or "human reconciliation marked execution as failed"
            if decision == "failed"
            else None
        )
        try:
            affected = await self.database.async_save(
                "UPDATE agent_tool_executions SET status = %s, result_content = %s, "
                "error_message = %s WHERE trace_id = %s AND tool_call_id = %s "
                "AND account_id = %s AND status = 'running'",
                (
                    decision,
                    result_content if decision == "completed" else None,
                    expected_error,
                    trace_id,
                    tool_call_id,
                    self.account_id,
                ),
            )
            if affected:
                return
            row = await self.database.async_fetch_one(
                "SELECT status, result_content, error_message FROM agent_tool_executions "
                "WHERE trace_id = %s AND tool_call_id = %s AND account_id = %s",
                params=(trace_id, tool_call_id, self.account_id),
            )
        except Exception as exc:
            raise ToolExecutionLedgerError("failed to resolve tool execution ledger") from exc
        if not row:
            raise ToolExecutionLedgerError("tool execution ledger record is missing")
        same_result = (
            row.get("status") == decision
            and (
                row.get("result_content") == result_content
                if decision == "completed"
                else row.get("error_message") == expected_error
            )
        )
        if not same_result:
            raise ToolExecutionLedgerError(
                "tool execution ledger was already resolved with a different outcome"
            )

    async def _finish(
        self,
        trace_id: str,
        tool_call_id: str,
        status: str,
        result_content: Optional[str],
        error_message: Optional[str],
    ) -> None:
        try:
            affected = await self.database.async_save(
                "UPDATE agent_tool_executions SET status = %s, result_content = %s, "
                "error_message = %s WHERE trace_id = %s AND tool_call_id = %s "
                "AND account_id = %s AND status = 'running'",
                (
                    status,
                    result_content,
                    error_message,
                    trace_id,
                    tool_call_id,
                    self.account_id,
                ),
            )
        except Exception as exc:
            raise ToolExecutionLedgerError("failed to finalize tool execution ledger") from exc
        if not affected:
            raise ToolExecutionLedgerError("tool execution ledger finalization lost ownership")


async def ensure_tool_execution_ledger(database: Any) -> None:
    """Create the additive ledger table for existing installations."""
    await database.async_save(CREATE_TOOL_EXECUTION_LEDGER_SQL)


__all__ = [
    "CREATE_TOOL_EXECUTION_LEDGER_SQL",
    "DBToolExecutionLedger",
    "LedgerClaim",
    "LedgerState",
    "ToolExecutionLedgerError",
    "ensure_tool_execution_ledger",
]
