# Agent Runtime V2

This iteration strengthens TaskPilot's existing runtime instead of replacing it with
another agent framework. It focuses on two production contracts: least-privilege tool
execution and resilient model calls.

## Per-run tool policy

`POST /api/agent/run` is read-only by default. Write and destructive tools must be
explicitly enabled for that run:

```json
{
  "goal": "Cancel the failed task",
  "tool_areas": ["task"],
  "max_steps": 8,
  "tool_policy": {
    "allowed_risk_levels": ["read", "write"],
    "allowed_tools": ["task_query_status", "task_cancel"],
    "blocked_tools": []
  }
}
```

The policy is enforced twice:

1. Only permitted tools are sent to the model.
2. The executor only accepts the exact tools advertised for that run.

The effective policy and step budget are returned by the API and included in run
metadata for traces and replay diagnostics.

## Human approval and durable resume

Write and destructive tools require human approval by default after they have been
explicitly enabled by `tool_policy`. The runtime freezes the complete tool-call batch
before executing any tool, publishes `approval_required`, and stores a versioned
checkpoint in `task_manager.data`. The task moves to status `5` (`WAITING_APPROVAL`).

Resolve the request with the exact `request_id` returned in `pending_approval`:

```http
POST /api/agent/runs/{trace_id}/approval
Content-Type: application/json

{
  "request_id": "apr-...",
  "decision": "approve",
  "reason": "reviewed change scope"
}
```

`decision` is either `approve` or `reject`. The authenticated account is always used as
the decision actor; a client-supplied actor cannot override it. Resolution atomically
claims the waiting task, so duplicate approval requests cannot execute a side effect
twice. Approval executes the frozen tool arguments without asking the model to recreate
them. Rejection inserts a structured tool error and lets the model continue safely.

Customize the approval gate per run:

```json
{
  "approval_policy": {
    "required_risk_levels": ["write", "destructive"],
    "required_tools": ["http_request"],
    "exempt_tools": []
  }
}
```

Trace sequence numbers resume from the persisted maximum after process restarts. A
paused run emits `run_paused` and `turn_paused`, not terminal `run_end`/`turn_end` events.

## Untrusted content and secret handling

Successful tool results are wrapped in an explicit `<tool_output>` data boundary before
they are sent back to the model. The system prompt tells the model that web, database,
retrieval, and tool content is untrusted data and must never override user or system
instructions. Runtime-generated errors keep their separate `Error:` protocol.

Common credential keys such as `authorization`, `cookie`, `password`, `secret`, `token`,
and `api_key` are recursively redacted from tool-call trace events, approval displays,
tool results, and persisted completed tool-call records. Redaction works on an observation
copy; the actual tool still receives its original arguments. A resumable approval
checkpoint necessarily retains the frozen original arguments in `task_manager.data`.
Deployments that allow credentials in model-generated tool arguments must therefore use
database encryption and strict access controls; secret references from a vault are the
preferred contract. TaskPilot does not yet encrypt checkpoint payloads itself.

Every tool receives a stable execution context containing `trace_id`, `step`, and
`tool_call_id`. `http_post` uses `<trace_id>:<tool_call_id>` as an automatic
`Idempotency-Key` unless the caller already supplied one. This protects cooperative HTTP
services from duplicate writes after an approval/resume crash.

HTTP Agent runs also use the additive `agent_tool_executions` ledger for every write or
destructive call. A completed call is replayed by `(trace_id, tool_call_id)` without
re-executing its handler. Reusing a call ID with different arguments is rejected. A
leftover `running` record is reported as `execution_in_doubt` and automatic retry stops;
this is deliberate at-most-once behavior for the crash window where a side effect may
have completed before its result was recorded. The table is created with
`CREATE TABLE IF NOT EXISTS` during startup. If it is unavailable, side-effecting Agent
tools fail closed while read-only service paths remain available.

An ambiguous call is a recoverable pause rather than a terminal failure. The task moves
to status `6` (`WAITING_RECONCILIATION`), publishes `reconciliation_required`, and stores
the frozen assistant message and a checkpoint. After verifying the downstream system,
an operator resolves the exact call ID:

```http
POST /api/agent/runs/{trace_id}/reconciliation
Content-Type: application/json

{
  "tool_call_id": "call-...",
  "decision": "completed",
  "result_content": "externally verified result",
  "reason": "verified in downstream audit log"
}
```

Use `decision: "failed"` only when external verification confirms that the side effect
did not complete. A completed decision supplies the tool result to the model; a failed
decision supplies a tool error. Neither decision re-executes the ambiguous call. The
authenticated account is the audit actor, the task status is claimed atomically, and a
conflicting second ledger decision is rejected. Audit history stores a result digest,
not the result body. Waiting reconciliation tasks can be cancelled like waiting approval
tasks.

This is not a general exactly-once claim. True exactly-once behavior still requires the
target side effect and ledger update to share a transaction, or a cooperative target that
honors the propagated idempotency key.

## LLM retries

Provider calls use bounded exponential backoff for rate limits, timeouts, connection
errors, and server-side HTTP failures. Authentication, validation, and other 4xx errors
are not retried. A stream can only be retried before its first token, preventing duplicate
output in SSE clients.

Every retry publishes an `llm_retry` trace event containing the current attempt, next
attempt, maximum attempts, delay, and error type.

Harness lifecycle events (`run_start`, `step_start`, `step_end`, `run_end`, and workflow
decisions) are now emitted to the shared trace bus as JSON-safe payloads. This closes the
previous gap where only token and tool events reached SSE and persistent traces.

When tools are available, TaskPilot uses a non-streaming model call so the complete tool
call payload is preserved. Text-only runs continue to stream tokens normally.

Environment configuration:

```text
LLM_TIMEOUT=30
LLM_MAX_RETRIES=2
LLM_RETRY_BACKOFF_SECONDS=1
```
