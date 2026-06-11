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

/** FE-1 mock：plan / strategy / reflection / reasoning 事件流 */
export function buildChatAgentEvents(traceId: string): TraceEvent[] {
  const now = new Date();
  const base = (s: number) => isoSecondsAgo(now, s);
  let seq = 0;
  const next = () => ++seq;

  return [
    {
      sequence: next(),
      type: 'chat.strategy',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(30),
      data: { mode: 'plan_execute' },
    },
    {
      sequence: next(),
      type: 'chat.plan_updated',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(28),
      data: {
        steps: [
          { id: '1', goal: '查询近期任务列表', status: 'done' },
          { id: '2', goal: '分析失败原因', status: 'in_progress' },
          { id: '3', goal: '生成修复建议', status: 'pending' },
        ],
      },
    },
    {
      sequence: next(),
      type: 'chat.reasoning_delta',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(25),
      data: { delta: '需要先拉取最近 24h 的失败任务…' },
    },
    {
      sequence: next(),
      type: 'chat.reflection',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(20),
      data: { text: '上一步工具返回为空，应缩小时间窗口重试。' },
    },
    {
      sequence: next(),
      type: 'chat.token_delta',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(15),
      data: { delta: '根据分析，建议优先检查 MySQL 连接池。' },
    },
    {
      sequence: next(),
      type: 'chat.turn_end',
      trace_id: traceId,
      step: null,
      source: 'chat',
      timestamp: base(10),
      data: {
        content: '根据分析，建议优先检查 MySQL 连接池。',
        token_usage: { prompt: 1200, completion: 180, total: 1380 },
      },
    },
  ];
}

/** FE-2 mock：菱形依赖 DAG（A→B,C→D） */
export function buildDagTraceEvents(traceId: string): TraceEvent[] {
  const now = new Date();
  const base = (s: number) => isoSecondsAgo(now, s);
  let seq = 0;
  const next = () => ++seq;

  const mkThink = (step: number, content: string, tools: string[] = []) => ({
    sequence: next(),
    type: 'think_end' as const,
    trace_id: traceId,
    step,
    source: 'harness' as const,
    timestamp: base(900 - step * 50),
    data: {
      assistant_message: {
        content,
        tool_calls: tools.map((name, i) => ({
          id: `call_${step}_${i}`,
          function: { name, arguments: '{}' },
        })),
      },
    },
  });

  return [
    {
      sequence: next(),
      type: 'run_start',
      trace_id: traceId,
      step: 0,
      source: 'harness',
      timestamp: base(950),
      data: { metadata: { goal: 'DAG demo: parallel subtasks' }, goal: 'DAG demo' },
    },
    { sequence: next(), type: 'step_start', trace_id: traceId, step: 1, source: 'harness', timestamp: base(940), data: {} },
    mkThink(1, '分解任务 A'),
    { sequence: next(), type: 'step_end', trace_id: traceId, step: 1, source: 'harness', timestamp: base(935), data: {} },
    { sequence: next(), type: 'step_start', trace_id: traceId, step: 2, source: 'harness', timestamp: base(930), data: { deps: [1] } },
    mkThink(2, '并行子任务 B', ['list_recent_tasks']),
    { sequence: next(), type: 'step_end', trace_id: traceId, step: 2, source: 'harness', timestamp: base(925), data: {} },
    { sequence: next(), type: 'step_start', trace_id: traceId, step: 3, source: 'harness', timestamp: base(920), data: { deps: [1] } },
    mkThink(3, '并行子任务 C', ['plan_tasks']),
    {
      sequence: next(),
      type: 'subagent_spawned',
      trace_id: traceId,
      step: 3,
      source: 'harness',
      timestamp: base(918),
      data: { child_trace_id: `${traceId}-sub-1` },
    },
    { sequence: next(), type: 'step_end', trace_id: traceId, step: 3, source: 'harness', timestamp: base(915), data: {} },
    { sequence: next(), type: 'step_start', trace_id: traceId, step: 4, source: 'harness', timestamp: base(910), data: { deps: [2, 3] } },
    mkThink(4, '汇总 B+C 结果'),
    {
      sequence: next(),
      type: 'handoff',
      trace_id: traceId,
      step: 4,
      source: 'harness',
      timestamp: base(908),
      data: { from_step: 4, to_step: 5, target_agent_id: 'reviewer' },
    },
    { sequence: next(), type: 'step_end', trace_id: traceId, step: 4, source: 'harness', timestamp: base(905), data: {} },
    { sequence: next(), type: 'step_start', trace_id: traceId, step: 5, source: 'harness', timestamp: base(900), data: { deps: [4] } },
    mkThink(5, '最终答复'),
    { sequence: next(), type: 'run_end', trace_id: traceId, step: 5, source: 'harness', timestamp: base(880), data: { result: { final_answer: 'done' } } },
  ];
}
