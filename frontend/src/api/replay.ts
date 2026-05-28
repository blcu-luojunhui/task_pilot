import { apiClient } from './client';
import type { ReplayRequest, ReplayResult } from './types';

export async function replayTrace(payload: ReplayRequest): Promise<ReplayResult> {
  const response = await apiClient.post<{ code: number; data: ReplayResult; message?: string }>(
    '/replay',
    payload
  );
  if (response.data.code !== 0) {
    throw new Error(response.data.message ?? 'Replay failed');
  }
  return response.data.data;
}
