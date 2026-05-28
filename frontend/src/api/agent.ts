import { apiClient, unwrap } from './client';

export interface RunAgentResponse {
  trace_id: string;
  tool_areas: string[];
}

export async function runAgentGoal(
  goal: string,
  toolAreas: string[],
): Promise<RunAgentResponse> {
  return unwrap(
    apiClient.post<{ data: RunAgentResponse }>('/agent/run', {
      goal,
      tool_areas: toolAreas,
    }),
  );
}

export interface ToolAreaInfo {
  tool_areas: string[];
}

export async function listToolAreas(): Promise<ToolAreaInfo> {
  return unwrap(
    apiClient.get<{ data: ToolAreaInfo }>('/agent/tool_areas'),
  );
}
