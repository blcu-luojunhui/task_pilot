import { apiClient, unwrap } from './client';

export interface EvalSummary {
  report_id: string;
  name: string;
  created_at: string;
  success_rate: number;
  avg_steps: number;
  avg_tokens: number;
  avg_latency_ms: number;
  tool_error_rate: number;
  case_count: number;
}

export interface EvalCase {
  case_id: string;
  goal: string;
  success: boolean;
  steps: number;
  tokens: number;
  latency_ms: number;
  judge_score: number | null;
  judge_reason: string | null;
  trace_id: string | null;
}

export interface EvalReport {
  summary: EvalSummary;
  cases: EvalCase[];
  trend: Array<{ date: string; success_rate: number }>;
}

export interface ListEvalReportsData {
  items: EvalSummary[];
}

export async function listEvalReports(): Promise<ListEvalReportsData> {
  return unwrap(apiClient.get<{ data: ListEvalReportsData }>('/evals/reports'));
}

export async function getEvalReport(reportId: string): Promise<EvalReport> {
  return unwrap(
    apiClient.get<{ data: EvalReport }>(`/evals/reports/${encodeURIComponent(reportId)}`),
  );
}
