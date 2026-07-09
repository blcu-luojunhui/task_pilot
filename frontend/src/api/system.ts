import { apiClient, unwrap } from './client';
import type { ApiRequestOptions, SystemStats } from './types';

export async function getSystemStats(options?: ApiRequestOptions): Promise<SystemStats> {
  return unwrap(
    apiClient.get<{ data: SystemStats }>('/system/stats', { signal: options?.signal }),
  );
}

export interface HealthData {
  status: 'healthy' | 'degraded' | 'unhealthy';
  checks: Record<string, string>;
}

export async function getHealth(): Promise<HealthData> {
  return unwrap(apiClient.get<{ data: HealthData }>('/health'));
}
