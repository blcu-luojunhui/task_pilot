import { apiClient, unwrap } from './client';
import type { SystemStats } from './types';

export async function getSystemStats(): Promise<SystemStats> {
  return unwrap(apiClient.get<{ data: SystemStats }>('/system/stats'));
}

export interface HealthData {
  status: 'healthy' | 'degraded' | 'unhealthy';
  checks: Record<string, string>;
}

export async function getHealth(): Promise<HealthData> {
  return unwrap(apiClient.get<{ data: HealthData }>('/health'));
}
