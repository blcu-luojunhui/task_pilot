import type { SkillInfo } from '@/api/types';

export const MOCK_SKILLS: SkillInfo[] = [
  {
    skill_id: 'sk_001',
    name: 'query_db',
    description: '执行 SELECT 查询，支持 task_manager / agent_events 等内部表',
    category: 'database',
    risk_level: 'READ',
    parameters: {
      sql: { type: 'string', description: '完整 SELECT 语句', required: true },
      limit: { type: 'integer', description: '最大行数', default: 100 },
    },
    call_count_24h: 247,
  },
  {
    skill_id: 'sk_002',
    name: 'http_get',
    description: '发起 HTTP GET 请求',
    category: 'http',
    risk_level: 'READ',
    parameters: {
      url: { type: 'string', description: '完整 URL', required: true },
      headers: { type: 'object', description: '自定义请求头' },
      timeout: { type: 'integer', description: '超时秒数', default: 10 },
    },
    call_count_24h: 89,
  },
  {
    skill_id: 'sk_003',
    name: 'cancel_task',
    description: '请求取消指定 trace_id 的任务（写入 CANCEL_REQUESTED）',
    category: 'task',
    risk_level: 'WRITE',
    parameters: {
      trace_id: { type: 'string', required: true },
    },
    call_count_24h: 12,
  },
  {
    skill_id: 'sk_004',
    name: 'now_iso',
    description: '获取当前 ISO 时间戳',
    category: 'utils',
    risk_level: 'READ',
    parameters: {},
    call_count_24h: 521,
  },
  {
    skill_id: 'sk_005',
    name: 'delete_records',
    description: '批量删除指定条件的记录（危险操作，需 PermissionGuard 放行）',
    category: 'database',
    risk_level: 'DESTRUCTIVE',
    parameters: {
      table: { type: 'string', required: true },
      where: { type: 'string', required: true, description: '必填，防止全表删除' },
    },
    call_count_24h: 0,
  },
];
