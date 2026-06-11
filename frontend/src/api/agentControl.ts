import { apiClient, unwrap } from './client';

export interface AgentControlResponse {
  code: number;
  message?: string;
  snapshot_id?: string;
}

export async function pauseAgent(traceId: string): Promise<AgentControlResponse> {
  return unwrap(
    apiClient.post<{ data: AgentControlResponse }>(`/agent/${traceId}/pause`),
  );
}

export async function resumeAgent(traceId: string): Promise<AgentControlResponse> {
  return unwrap(
    apiClient.post<{ data: AgentControlResponse }>(`/agent/${traceId}/resume`),
  );
}

export async function stopAgent(traceId: string): Promise<AgentControlResponse> {
  return unwrap(
    apiClient.post<{ data: AgentControlResponse }>(`/agent/${traceId}/stop`),
  );
}

export async function saveSnapshot(traceId: string): Promise<AgentControlResponse> {
  return unwrap(
    apiClient.post<{ data: AgentControlResponse }>(`/agent/${traceId}/snapshot`),
  );
}

export async function runFromSnapshot(
  traceId: string,
  snapshotId: string,
): Promise<AgentControlResponse & { trace_id?: string }> {
  return unwrap(
    apiClient.post<{ data: AgentControlResponse & { trace_id?: string } }>(
      `/agent/${traceId}/run_from_snapshot`,
      { snapshot_id: snapshotId },
    ),
  );
}
