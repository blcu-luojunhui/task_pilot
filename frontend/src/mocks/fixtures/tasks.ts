import { TaskStatus, type TaskDetail, type TaskSummary } from '@/api/types';

/**
 * Mock 任务数据
 *
 * 这些 trace_id 故意拼成"Agent-YYYYmmddHHMMSS-xxxxxxxxxxxxxxxx"风格，
 * 与 src/core/agents/state/utils.py 的 generate_agent_trace_id 输出一致。
 */

function ts(daysAgo: number, secondsAgo = 0): number {
  return Math.floor(Date.now() / 1000) - daysAgo * 86400 - secondsAgo;
}

export const MOCK_TASKS: TaskSummary[] = [
  {
    trace_id: 'Agent-20260513184501-a1b2c3d4e5f60001',
    task_name: 'system_health_check',
    date_string: '2026-05-13',
    task_status: TaskStatus.PROCESSING,
    start_timestamp: ts(0, 35),
    finish_timestamp: null,
    data: { check_targets: ['mysql', 'redis', 'log_service'], retry: 0 },
  },
  {
    trace_id: 'Agent-20260513184130-b2c3d4e5f6a70002',
    task_name: 'data_etl_daily',
    date_string: '2026-05-13',
    task_status: TaskStatus.PROCESSING,
    start_timestamp: ts(0, 250),
    finish_timestamp: null,
    data: { source: 'orders', target: 'warehouse.fact_orders' },
  },
  {
    trace_id: 'Agent-20260513183020-c3d4e5f6a7b80003',
    task_name: 'system_health_check',
    date_string: '2026-05-13',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(0, 900),
    finish_timestamp: ts(0, 880),
    data: { check_targets: ['mysql', 'redis'], retry: 0 },
  },
  {
    trace_id: 'Agent-20260513173015-d4e5f6a7b8c90004',
    task_name: 'log_anomaly_detect',
    date_string: '2026-05-13',
    task_status: TaskStatus.FAILED,
    start_timestamp: ts(0, 4200),
    finish_timestamp: ts(0, 4080),
    data: {
      window_minutes: 30,
      error: 'LLM tool_call returned malformed JSON after truncation',
    },
  },
  {
    trace_id: 'Agent-20260513120015-e5f6a7b8c9d00005',
    task_name: 'data_etl_daily',
    date_string: '2026-05-13',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(0, 28800),
    finish_timestamp: ts(0, 28200),
    data: { source: 'orders', target: 'warehouse.fact_orders' },
  },
  {
    trace_id: 'Agent-20260513093011-f6a7b8c9d0e10006',
    task_name: 'report_generation',
    date_string: '2026-05-13',
    task_status: TaskStatus.CANCELLED,
    start_timestamp: ts(0, 39600),
    finish_timestamp: ts(0, 39400),
    data: { report_type: 'weekly_summary', recipients: ['ops@example.com'] },
  },
  {
    trace_id: 'Agent-20260512235011-a7b8c9d0e1f20007',
    task_name: 'system_health_check',
    date_string: '2026-05-12',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(1, 0),
    finish_timestamp: ts(1, -30),
    data: { check_targets: ['mysql'], retry: 0 },
  },
  {
    trace_id: 'Agent-20260512200012-b8c9d0e1f2a30008',
    task_name: 'data_etl_daily',
    date_string: '2026-05-12',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(1, 14400),
    finish_timestamp: ts(1, 13800),
    data: { source: 'orders', target: 'warehouse.fact_orders' },
  },
  {
    trace_id: 'Agent-20260512180013-c9d0e1f2a3b40009',
    task_name: 'log_anomaly_detect',
    date_string: '2026-05-12',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(1, 21600),
    finish_timestamp: ts(1, 21450),
    data: { window_minutes: 30 },
  },
  {
    trace_id: 'Agent-20260512090014-d0e1f2a3b4c5000a',
    task_name: 'report_generation',
    date_string: '2026-05-12',
    task_status: TaskStatus.FAILED,
    start_timestamp: ts(1, 54000),
    finish_timestamp: ts(1, 53400),
    data: { report_type: 'weekly_summary', error: 'task timeout (1800s)' },
  },
  {
    trace_id: 'Agent-20260511234015-e1f2a3b4c5d6000b',
    task_name: 'data_etl_daily',
    date_string: '2026-05-11',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(2, 0),
    finish_timestamp: ts(2, -500),
    data: {},
  },
  {
    trace_id: 'Agent-20260511180016-f2a3b4c5d6e7000c',
    task_name: 'system_health_check',
    date_string: '2026-05-11',
    task_status: TaskStatus.SUCCESS,
    start_timestamp: ts(2, 21600),
    finish_timestamp: ts(2, 21570),
    data: {},
  },
];

/** trace_id → 详情扩展（含 agent_metadata） */
export const MOCK_TASK_DETAILS: Record<string, Partial<TaskDetail>> = {
  'Agent-20260513183020-c3d4e5f6a7b80003': {
    agent_metadata: {
      goal: '检查 mysql 和 redis 的健康状态，生成简报',
      stop_reason: 'model_final',
      total_steps: 4,
      tool_calls_count: 5,
      duration_seconds: 17.4,
      token_usage: { prompt: 2103, completion: 1318, total: 3421 },
      final_answer:
        '系统状态：MySQL 健康（连接池利用率 23%），Redis 健康（响应时间 1.2ms）。无异常。',
    },
  },
  'Agent-20260513173015-d4e5f6a7b8c90004': {
    agent_metadata: {
      goal: '检测最近 30 分钟内的异常日志，分类汇总',
      stop_reason: 'error',
      total_steps: 6,
      tool_calls_count: 8,
      duration_seconds: 121.3,
      token_usage: { prompt: 5240, completion: 2150, total: 7390 },
      final_answer: null,
    },
  },
};

export function findTaskByTraceId(traceId: string): TaskSummary | undefined {
  return MOCK_TASKS.find((t) => t.trace_id === traceId);
}
