import type { SkillInfo } from '@/api/types';

function systemMarkdown(skill: Omit<SkillInfo, 'markdown' | 'source' | 'editable'>): string {
  return [
    '---',
    `name: ${skill.name}`,
    `description: ${skill.description}`,
    `category: ${skill.category}`,
    'skill_type: executable',
    `risk_level: ${String(skill.risk_level).toLowerCase()}`,
    '---',
    '',
    '## Description',
    '',
    skill.description,
    '',
    '## Parameters',
    '',
    '```json',
    JSON.stringify(skill.parameters, null, 4),
    '```',
    '',
  ].join('\n');
}

const SYSTEM_SKILLS: Array<Omit<SkillInfo, 'markdown' | 'source' | 'editable'>> = [
  {
    skill_id: 'sk_001',
    name: 'db_query',
    description: '从 MySQL 数据库查询数据，返回多行结果。仅支持 SELECT 语句。',
    category: 'database',
    risk_level: 'read',
    skill_type: 'executable',
    parameters: {
      query: { type: 'string', description: 'SQL SELECT 语句', required: true },
      params: { type: 'array', description: '查询参数' },
    },
    call_count_24h: 247,
  },
  {
    skill_id: 'sk_002',
    name: 'http_get',
    description: '发送 HTTP GET 请求，获取数据',
    category: 'http',
    risk_level: 'read',
    skill_type: 'executable',
    parameters: {
      url: { type: 'string', description: '完整 URL', required: true },
    },
    call_count_24h: 89,
  },
  {
    skill_id: 'sk_003',
    name: 'task_cancel',
    description: '请求取消任务（设置取消信号，任务会在下次轮询时取消）',
    category: 'task',
    risk_level: 'write',
    skill_type: 'executable',
    parameters: {
      trace_id: { type: 'string', required: true },
    },
    call_count_24h: 12,
  },
  {
    skill_id: 'sk_004',
    name: 'util_current_time',
    description: '获取当前时间（ISO 格式字符串）',
    category: 'utils',
    risk_level: 'read',
    skill_type: 'executable',
    parameters: {},
    call_count_24h: 521,
  },
  {
    skill_id: 'sk_005',
    name: 'run_task',
    description: '启动一个 TaskPilot 业务任务',
    category: 'chat_ops',
    risk_level: 'write',
    skill_type: 'executable',
    parameters: {
      task_name: { type: 'string', required: true },
    },
    call_count_24h: 0,
  },
];

export const MOCK_SKILLS: SkillInfo[] = SYSTEM_SKILLS.map((skill) => ({
  ...skill,
  source: 'system',
  editable: false,
  markdown: systemMarkdown(skill),
}));

let personalSkillSeq = 1;
export const MOCK_PERSONAL_SKILLS: SkillInfo[] = [
  {
    skill_id: '1',
    name: 'my-runbook',
    description: '个人运维 runbook',
    category: 'general',
    risk_level: 'read',
    skill_type: 'knowledge',
    parameters: {},
    source: 'personal',
    editable: true,
    markdown: [
      '---',
      'name: my-runbook',
      'description: 个人运维 runbook',
      'category: general',
      'skill_type: knowledge',
      'scope: agent:*',
      '---',
      '',
      '## Description',
      '',
      '记录我个人常用的排查步骤。',
      '',
      '## Guidelines',
      '',
      '- 先看 /api/health',
      '- 再查 task_manager 最近失败任务',
      '',
    ].join('\n'),
  },
];

export function nextPersonalSkillId(): string {
  personalSkillSeq += 1;
  return String(personalSkillSeq);
}

export function resetPersonalSkillSeq(): void {
  personalSkillSeq = MOCK_PERSONAL_SKILLS.length;
}
