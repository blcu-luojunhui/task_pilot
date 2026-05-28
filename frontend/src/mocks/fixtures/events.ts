import type { TraceEvent } from '@/api/types';

/**
 * 真实 trace 事件 mock
 *
 * 完整覆盖 task.accepted → run_start → step_start → think_* → act_* → step_end → run_end → task.finished
 * 用于 TraceView 演示。后端 P0/P1 修复完后可换成真数据。
 */

function isoSecondsAgo(base: Date, seconds: number): string {
  return new Date(base.getTime() - seconds * 1000).toISOString();
}

export function buildSuccessTraceEvents(traceId: string): TraceEvent[] {
  const now = new Date();
  const base = (s: number) => isoSecondsAgo(now, s);

  let seq = 0;
  const next = () => ++seq;

  return [
    {
      sequence: next(),
      type: 'task.accepted',
      trace_id: traceId,
      step: null,
      source: 'task_scheduler',
      timestamp: base(900),
      data: { task_name: 'system_health_check' },
    },
    {
      sequence: next(),
      type: 'task.started',
      trace_id: traceId,
      step: null,
      source: 'task_scheduler',
      timestamp: base(899),
      data: { task_name: 'system_health_check' },
    },
    {
      sequence: next(),
      type: 'run_start',
      trace_id: traceId,
      step: 0,
      source: 'harness',
      timestamp: base(898),
      data: { metadata: { goal: '检查 mysql 和 redis 的健康状态，生成简报' } },
    },
    // ---- step 1 ----
    {
      sequence: next(),
      type: 'step_start',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(897),
      data: {},
    },
    {
      sequence: next(),
      type: 'think_start',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(897),
      data: {},
    },
    {
      sequence: next(),
      type: 'think_end',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(896),
      data: {
        assistant_message: {
          role: 'assistant',
          content: '我需要先检查数据库连接状态，看看连接池利用率',
          tool_calls: [
            {
              id: 'call_1',
              type: 'function',
              function: {
                name: 'query_db',
                arguments: '{"sql": "SHOW STATUS LIKE \'Threads_connected\'"}',
              },
            },
          ],
        },
        token_usage: { prompt: 520, completion: 88 },
      },
    },
    {
      sequence: next(),
      type: 'act_start',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(895),
      data: {
        tool_calls: [
          {
            id: 'call_1',
            name: 'query_db',
            arguments: { sql: "SHOW STATUS LIKE 'Threads_connected'" },
          },
        ],
      },
    },
    {
      sequence: next(),
      type: 'act_end',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(894),
      data: {
        tool_results: [
          {
            tool_call_id: 'call_1',
            content: '{"rows": [{"Variable_name": "Threads_connected", "Value": "23"}]}',
          },
        ],
      },
    },
    {
      sequence: next(),
      type: 'step_end',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(894),
      data: {},
    },
    // ---- step 2 ----
    {
      sequence: next(),
      type: 'step_start',
      trace_id: traceId,
      step: 2,
      source: 'harness',
      timestamp: base(893),
      data: {},
    },
    {
      sequence: next(),
      type: 'think_end',
      trace_id: traceId,
      step: 2,
      source: 'harness',
      timestamp: base(892),
      data: {
        assistant_message: {
          role: 'assistant',
          content: '数据库连接 23，正常。下一步检查 Redis 响应时间和最近错误数。',
          tool_calls: [
            { id: 'call_2a', type: 'function', function: { name: 'http_get', arguments: '{"url": "http://redis:6379/ping"}' } },
            { id: 'call_2b', type: 'function', function: { name: 'query_db', arguments: '{"sql": "SELECT COUNT(*) FROM task_manager WHERE task_status=99"}' } },
          ],
        },
        token_usage: { prompt: 620, completion: 130 },
      },
    },
    {
      sequence: next(),
      type: 'act_end',
      trace_id: traceId,
      step: 2,
      source: 'harness',
      timestamp: base(891),
      data: {
        tool_results: [
          { tool_call_id: 'call_2a', content: 'PONG (1.2ms)' },
          { tool_call_id: 'call_2b', content: '{"count": 0}' },
        ],
      },
    },
    {
      sequence: next(),
      type: 'step_end',
      trace_id: traceId,
      step: 2,
      source: 'harness',
      timestamp: base(890),
      data: {},
    },
    // ---- step 3: 最终回答 ----
    {
      sequence: next(),
      type: 'think_end',
      trace_id: traceId,
      step: 3,
      source: 'harness',
      timestamp: base(888),
      data: {
        assistant_message: {
          role: 'assistant',
          content:
            '系统状态：MySQL 健康（连接池利用率 23%），Redis 健康（响应时间 1.2ms）。无异常。',
        },
        token_usage: { prompt: 850, completion: 60 },
      },
    },
    {
      sequence: next(),
      type: 'run_end',
      trace_id: traceId,
      step: 3,
      source: 'harness',
      timestamp: base(887),
      data: {
        result: { stop_reason: 'model_final', success: true, total_steps: 3 },
      },
    },
    {
      sequence: next(),
      type: 'task.finished',
      trace_id: traceId,
      step: null,
      source: 'task_scheduler',
      timestamp: base(887),
      data: { task_name: 'system_health_check', status: '2', duration_seconds: 13.4 },
    },
  ];
}

/** 失败 trace 的事件流（演示 act_end error + run_error） */
export function buildFailedTraceEvents(traceId: string): TraceEvent[] {
  const now = new Date();
  const base = (s: number) => isoSecondsAgo(now, s);
  let seq = 0;
  const next = () => ++seq;

  return [
    {
      sequence: next(),
      type: 'task.accepted',
      trace_id: traceId,
      step: null,
      source: 'task_scheduler',
      timestamp: base(4200),
      data: { task_name: 'log_anomaly_detect' },
    },
    {
      sequence: next(),
      type: 'run_start',
      trace_id: traceId,
      step: 0,
      source: 'harness',
      timestamp: base(4199),
      data: { metadata: { goal: '检测最近 30 分钟内的异常日志' } },
    },
    {
      sequence: next(),
      type: 'think_end',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(4195),
      data: {
        assistant_message: {
          role: 'assistant',
          content: '我需要从 task_manager 表拉取所有失败的任务记录',
          tool_calls: [
            {
              id: 'call_x1',
              type: 'function',
              function: {
                name: 'query_db',
                arguments: '{"sql": "SELECT * FROM task_manager WHERE task_status=99"}',
              },
            },
          ],
        },
      },
    },
    {
      sequence: next(),
      type: 'act_end',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(4190),
      data: {
        tool_results: [
          {
            tool_call_id: 'call_x1',
            content:
              'Error: LLM tool_call returned malformed JSON after truncation (P0-1 还没修)',
          },
        ],
      },
    },
    {
      sequence: next(),
      type: 'run_error',
      trace_id: traceId,
      step: 1,
      source: 'harness',
      timestamp: base(4080),
      data: { error: 'consecutive errors exceeded threshold' },
    },
    {
      sequence: next(),
      type: 'task.finished',
      trace_id: traceId,
      step: null,
      source: 'task_scheduler',
      timestamp: base(4080),
      data: { task_name: 'log_anomaly_detect', status: '99', duration_seconds: 120.3 },
    },
  ];
}
