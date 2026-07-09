import { apiClient, unwrap } from './client';

export interface RunAgentResponse {
  trace_id: string;
  tool_areas: string[];
}

export async function runAgentGoal(
  goal: string,
  toolAreas: string[],
  originalGoal?: string,
): Promise<RunAgentResponse> {
  return unwrap(
    apiClient.post<{ data: RunAgentResponse }>('/agent/run', {
      goal,
      tool_areas: toolAreas,
      original_goal: originalGoal || undefined,
    }),
  );
}

export interface ToolAreaInfo {
  tool_areas: string[];
}

export interface GeneratePrdResponse {
  prd: string;
}

export async function generatePrd(goal: string): Promise<GeneratePrdResponse> {
  return unwrap(
    apiClient.post<{ data: GeneratePrdResponse }>('/agent/generate_prd', {
      goal,
    }),
  );
}

export async function listToolAreas(): Promise<ToolAreaInfo> {
  return unwrap(
    apiClient.get<{ data: ToolAreaInfo }>('/agent/tool_areas'),
  );
}
