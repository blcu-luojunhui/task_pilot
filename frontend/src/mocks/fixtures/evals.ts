import type { EvalReport, EvalSummary } from '@/api/eval';

export const MOCK_EVAL_SUMMARIES: EvalSummary[] = [
  {
    report_id: 'eval-2026-06-01',
    name: 'Agent regression v4',
    created_at: '2026-06-01T10:00:00Z',
    success_rate: 0.82,
    avg_steps: 4.3,
    avg_tokens: 2180,
    avg_latency_ms: 12400,
    tool_error_rate: 0.06,
    case_count: 50,
  },
  {
    report_id: 'eval-2026-05-25',
    name: 'Agent regression v3',
    created_at: '2026-05-25T10:00:00Z',
    success_rate: 0.76,
    avg_steps: 5.1,
    avg_tokens: 2450,
    avg_latency_ms: 14200,
    tool_error_rate: 0.09,
    case_count: 48,
  },
];

export const MOCK_EVAL_REPORTS: Record<string, EvalReport> = {
  'eval-2026-06-01': {
    summary: MOCK_EVAL_SUMMARIES[0],
    trend: [
      { date: '05-28', success_rate: 0.74 },
      { date: '05-29', success_rate: 0.78 },
      { date: '05-30', success_rate: 0.8 },
      { date: '06-01', success_rate: 0.82 },
    ],
    cases: [
      {
        case_id: 'case-001',
        goal: '列出最近失败任务并总结原因',
        success: true,
        steps: 3,
        tokens: 1800,
        latency_ms: 9800,
        judge_score: 0.92,
        judge_reason: '准确识别失败模式',
        trace_id: 'Agent-20260601120000-abc123',
      },
      {
        case_id: 'case-002',
        goal: '提交 health_check 并等待结果',
        success: false,
        steps: 6,
        tokens: 3200,
        latency_ms: 21000,
        judge_score: 0.41,
        judge_reason: '未正确等待任务完成',
        trace_id: 'Agent-20260601120500-def456',
      },
      {
        case_id: 'case-003',
        goal: '规划三个子任务并行执行',
        success: true,
        steps: 5,
        tokens: 2600,
        latency_ms: 15600,
        judge_score: 0.88,
        judge_reason: '计划合理，执行完整',
        trace_id: 'Agent-20260601121000-ghi789',
      },
    ],
  },
};
