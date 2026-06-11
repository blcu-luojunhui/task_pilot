import { http, HttpResponse } from 'msw';
import { TaskStatus, type SystemStats, type TaskSummary } from '@/api/types';
import { findTaskByTraceId, MOCK_TASK_DETAILS, MOCK_TASKS } from './fixtures/tasks';
import { buildFailedTraceEvents, buildSuccessTraceEvents } from './fixtures/events';
import { MOCK_EVAL_REPORTS, MOCK_EVAL_SUMMARIES } from './fixtures/evals';
import { MOCK_SKILLS, MOCK_PERSONAL_SKILLS, nextPersonalSkillId } from './fixtures/skills';

/** 内存可变副本，支持 mock 期间提交 / 取消 */
const taskState: TaskSummary[] = MOCK_TASKS.map((t) => ({ ...t, data: { ...t.data } }));

function makeTraceId(): string {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const hh = String(now.getHours()).padStart(2, '0');
  const mi = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  const rand = Math.random().toString(36).slice(2, 18).padEnd(16, '0').slice(0, 16);
  return `Agent-${yyyy}${mm}${dd}${hh}${mi}${ss}-${rand}`;
}

function ok<T>(data: T) {
  return HttpResponse.json({ code: 0, message: 'ok', data });
}

function err(code: number, message: string, status = 400) {
  return HttpResponse.json({ code, message }, { status });
}

export const handlers = [
  // ============ GET /api/tasks ============
  http.get('/api/tasks', ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.getAll('status').map((s) => Number(s));
    const taskName = url.searchParams.get('task_name')?.toLowerCase();
    const traceIdFilter = url.searchParams.get('trace_id');
    const date = url.searchParams.get('date');
    const page = Number(url.searchParams.get('page') ?? 1);
    const pageSize = Number(url.searchParams.get('page_size') ?? 20);

    let filtered = [...taskState];
    if (status.length > 0) filtered = filtered.filter((t) => status.includes(t.task_status));
    if (taskName) filtered = filtered.filter((t) => t.task_name.toLowerCase().includes(taskName));
    if (traceIdFilter) filtered = filtered.filter((t) => t.trace_id.includes(traceIdFilter));
    if (date) filtered = filtered.filter((t) => t.date_string === date);

    filtered.sort((a, b) => b.start_timestamp - a.start_timestamp);
    const total = filtered.length;
    const items = filtered.slice((page - 1) * pageSize, page * pageSize);

    return ok({ total, page, page_size: pageSize, items });
  }),

  // ============ GET /api/tasks/:trace_id ============
  http.get('/api/tasks/:traceId', ({ params }) => {
    const { traceId } = params;
    const task = taskState.find((t) => t.trace_id === traceId);
    if (!task) return err(404, 'task not found', 404);
    const extra = MOCK_TASK_DETAILS[traceId as string] ?? {};
    return ok({ ...task, ...extra });
  }),

  // ============ GET /api/tasks/:trace_id/events ============
  http.get('/api/tasks/:traceId/events', ({ params }) => {
    const traceId = String(params.traceId);
    const task = findTaskByTraceId(traceId);
    if (!task) return err(404, 'task not found', 404);

    const events =
      task.task_status === TaskStatus.FAILED
        ? buildFailedTraceEvents(traceId)
        : buildSuccessTraceEvents(traceId);

    const closed =
      task.task_status === TaskStatus.SUCCESS ||
      task.task_status === TaskStatus.FAILED ||
      task.task_status === TaskStatus.CANCELLED;

    return ok({ trace_id: traceId, closed, events });
  }),

  // ============ POST /api/run_task ============
  http.post('/api/run_task', async ({ request }) => {
    const body = (await request.json()) as { task_name?: string; date_string?: string };
    if (!body.task_name) {
      return HttpResponse.json(
        { code: 1001, message: 'task_name is required' },
        { status: 400 }
      );
    }
    const traceId = makeTraceId();
    const newTask: TaskSummary = {
      trace_id: traceId,
      task_name: body.task_name,
      date_string: body.date_string ?? new Date().toISOString().slice(0, 10),
      task_status: TaskStatus.PROCESSING,
      start_timestamp: Math.floor(Date.now() / 1000),
      finish_timestamp: null,
      data: { ...body },
    };
    taskState.unshift(newTask);
    return HttpResponse.json({
      code: 0,
      message: 'Task started successfully',
      trace_id: traceId,
      data: { code: 0, message: 'Task started successfully', trace_id: traceId },
    });
  }),

  // ============ POST /api/cancel_task ============
  http.post('/api/cancel_task', async ({ request }) => {
    const body = (await request.json()) as { trace_id?: string };
    const traceId = body.trace_id;
    if (!traceId) return err(1001, 'trace_id is required');
    const task = taskState.find((t) => t.trace_id === traceId);
    if (!task) {
      return HttpResponse.json({
        code: 1,
        message: 'task not found or already finished',
        trace_id: traceId,
      });
    }
    if (task.task_status === TaskStatus.PROCESSING) {
      task.task_status = TaskStatus.CANCEL_REQUESTED;
    } else if (task.task_status === TaskStatus.INIT) {
      task.task_status = TaskStatus.CANCELLED;
      task.finish_timestamp = Math.floor(Date.now() / 1000);
    }
    return HttpResponse.json({
      code: 0,
      message: 'cancel requested',
      trace_id: traceId,
    });
  }),

  // ============ GET /api/skills ============
  http.get('/api/skills', () => ok([...MOCK_SKILLS, ...MOCK_PERSONAL_SKILLS])),

  http.get('/api/skills/personal/template', ({ request }) => {
    const url = new URL(request.url);
    const name = url.searchParams.get('name') ?? 'new-skill';
    const category = url.searchParams.get('category') ?? 'chat_ops';
    const markdown = [
      '---',
      `name: ${name}`,
      'description: 在此填写简短描述',
      `category: ${category}`,
      'skill_type: knowledge',
      'scope: agent:*',
      '---',
      '',
      '## Description',
      '',
      '在此描述 skill 的用途与触发场景。',
      '',
      '## Guidelines',
      '',
      '',
    ].join('\n');
    return ok({ markdown });
  }),

  http.post('/api/skills/personal', async ({ request }) => {
    const body = (await request.json()) as { content?: string };
    const content = body.content ?? '';
    const nameMatch = content.match(/^name:\s*(.+)$/m);
    const categoryMatch = content.match(/^category:\s*(.+)$/m);
    const descMatch = content.match(/^description:\s*(.+)$/m);
    const skill: (typeof MOCK_PERSONAL_SKILLS)[number] = {
      skill_id: nextPersonalSkillId(),
      name: nameMatch?.[1]?.trim() ?? 'new-skill',
      description: descMatch?.[1]?.trim() ?? '',
      category: categoryMatch?.[1]?.trim() ?? 'general',
      risk_level: 'read',
      skill_type: 'knowledge',
      parameters: {},
      source: 'personal',
      editable: true,
      markdown: content,
    };
    MOCK_PERSONAL_SKILLS.push(skill);
    return ok(skill);
  }),

  http.put('/api/skills/personal/:skillId', async ({ params, request }) => {
    const skillId = String(params.skillId);
    const body = (await request.json()) as { content?: string };
    const idx = MOCK_PERSONAL_SKILLS.findIndex((s) => s.skill_id === skillId);
    if (idx < 0) return err(404, 'Skill not found', 404);
    const content = body.content ?? '';
    const nameMatch = content.match(/^name:\s*(.+)$/m);
    const categoryMatch = content.match(/^category:\s*(.+)$/m);
    const descMatch = content.match(/^description:\s*(.+)$/m);
    MOCK_PERSONAL_SKILLS[idx] = {
      ...MOCK_PERSONAL_SKILLS[idx],
      name: nameMatch?.[1]?.trim() ?? MOCK_PERSONAL_SKILLS[idx].name,
      description: descMatch?.[1]?.trim() ?? MOCK_PERSONAL_SKILLS[idx].description,
      category: categoryMatch?.[1]?.trim() ?? MOCK_PERSONAL_SKILLS[idx].category,
      markdown: content,
    };
    return ok(MOCK_PERSONAL_SKILLS[idx]);
  }),

  http.delete('/api/skills/personal/:skillId', ({ params }) => {
    const skillId = String(params.skillId);
    const idx = MOCK_PERSONAL_SKILLS.findIndex((s) => s.skill_id === skillId);
    if (idx < 0) return err(404, 'Skill not found', 404);
    MOCK_PERSONAL_SKILLS.splice(idx, 1);
    return ok({ deleted: true, skill_id: skillId });
  }),

  // ============ GET /api/system/stats ============
  http.get('/api/system/stats', () => {
    const counts = {
      running:
        taskState.filter(
          (t) =>
            t.task_status === TaskStatus.PROCESSING ||
            t.task_status === TaskStatus.CANCEL_REQUESTED
        ).length,
      success_24h: taskState.filter((t) => t.task_status === TaskStatus.SUCCESS).length,
      failed_24h: taskState.filter((t) => t.task_status === TaskStatus.FAILED).length,
      cancelled_24h: taskState.filter((t) => t.task_status === TaskStatus.CANCELLED).length,
    };
    const stats: SystemStats = {
      health: { mysql: 'ok', log_service: 'ok' },
      counts,
      throughput_24h: Array.from({ length: 24 }, (_, i) => ({
        hour: `${String(i).padStart(2, '0')}:00`,
        success: Math.floor(Math.random() * 20 + 5),
        failed: Math.floor(Math.random() * 3),
      })),
      recent_failures: taskState
        .filter((t) => t.task_status === TaskStatus.FAILED)
        .slice(0, 5)
        .map((t) => ({
          ...t,
          error: (t.data as Record<string, string>).error ?? 'unknown error',
        })),
    };
    return ok(stats);
  }),

  // ============ GET /api/health ============
  http.get('/api/health', () =>
    ok({
      status: 'healthy',
      checks: { mysql: 'ok', log_service: 'ok' },
    })
  ),

  // ============ FE-8 Evals ============
  http.get('/api/evals/reports', () => ok({ items: MOCK_EVAL_SUMMARIES })),
  http.get('/api/evals/reports/:reportId', ({ params }) => {
    const report = MOCK_EVAL_REPORTS[String(params.reportId)];
    if (!report) return err(404, 'report not found', 404);
    return ok(report);
  }),

  // ============ FE-4 Agent 生命周期控制（mock） ============
  http.post('/api/agent/:traceId/pause', () => ok({ code: 0, message: 'paused' })),
  http.post('/api/agent/:traceId/resume', () => ok({ code: 0, message: 'resumed' })),
  http.post('/api/agent/:traceId/stop', () => ok({ code: 0, message: 'stopped' })),
  http.post('/api/agent/:traceId/snapshot', () =>
    ok({ code: 0, message: 'saved', snapshot_id: `snap-${Date.now()}` }),
  ),
  http.post('/api/agent/:traceId/run_from_snapshot', async ({ request }) => {
    const body = (await request.json()) as { snapshot_id?: string };
    return ok({
      code: 0,
      message: 'replayed',
      trace_id: makeTraceId(),
      snapshot_id: body.snapshot_id,
    });
  }),

  // ============ FE-3 工件读取（mock） ============
  http.get('/api/artifacts/:artifactId', ({ params, request }) => {
    const url = new URL(request.url);
    const offset = Number(url.searchParams.get('offset') ?? 0);
    const full = `Mock artifact content for ${params.artifactId}\n`.repeat(40);
    const slice = full.slice(offset, offset + 8000);
    return ok({
      id: String(params.artifactId),
      content: slice,
      offset,
      has_more: offset + slice.length < full.length,
      total_size: full.length,
    });
  }),
];
