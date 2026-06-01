import { apiClient, unwrap } from './client';
import type { SkillCallsData, SkillInfo } from './types';

export async function listSkills(): Promise<SkillInfo[]> {
  return unwrap(apiClient.get<{ data: SkillInfo[] }>('/skills'));
}

export async function getPersonalSkillTemplate(
  name = 'new-skill',
  category = 'chat_ops'
): Promise<string> {
  const data = await unwrap(
    apiClient.get<{ data: { markdown: string } }>('/skills/personal/template', {
      params: { name, category },
    })
  );
  return data.markdown;
}

export async function createPersonalSkill(content: string): Promise<SkillInfo> {
  return unwrap(
    apiClient.post<{ data: SkillInfo }>('/skills/personal', { content })
  );
}

export async function updatePersonalSkill(
  skillId: string,
  content: string
): Promise<SkillInfo> {
  return unwrap(
    apiClient.put<{ data: SkillInfo }>(`/skills/personal/${skillId}`, { content })
  );
}

export async function deletePersonalSkill(skillId: string): Promise<void> {
  await unwrap(
    apiClient.delete<{ data: { deleted: boolean } }>(`/skills/personal/${skillId}`)
  );
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
