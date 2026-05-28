import { apiClient, unwrap } from './client';
import type { SkillCallsData, SkillInfo } from './types';

export async function listSkills(): Promise<SkillInfo[]> {
  return unwrap(apiClient.get<{ data: SkillInfo[] }>('/skills'));
}

export async function getSkillCalls(
  skillName: string,
  limit = 50
): Promise<SkillCallsData> {
  return unwrap(
    apiClient.get<{ data: SkillCallsData }>(
      `/skills/${encodeURIComponent(skillName)}/calls`,
      { params: { limit } }
    )
  );
}
