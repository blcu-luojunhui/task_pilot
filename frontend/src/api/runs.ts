import { apiClient, unwrap } from './client';
import type { ListRunsData, ListRunsParams } from './types';

export async function listRuns(params: ListRunsParams = {}): Promise<ListRunsData> {
  return unwrap(
    apiClient.get<{ data: ListRunsData }>('/runs', {
      params,
    })
  );
}
