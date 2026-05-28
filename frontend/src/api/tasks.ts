import { apiClient, unwrap } from './client';
import type {
  CancelTaskRequest,
  ListTasksData,
  ListTasksParams,
  RunTaskRequest,
  RunTaskResponse,
  TaskDetail,
  TraceEventsData,
} from './types';

/** 列出任务，支持状态/任务名/日期/trace_id 多维筛选 */
export async function listTasks(params: ListTasksParams = {}): Promise<ListTasksData> {
  // status 数组转 status=2&status=99 形式（后端按 querystring 多值解析）
  return unwrap(
    apiClient.get<{ data: ListTasksData }>('/tasks', {
      params,
      paramsSerializer: {
        indexes: null, // status=2&status=99 而不是 status[0]=2
      },
    })
  );
}

/** 单任务详情（含 agent_metadata 子字段） */
export async function getTaskDetail(traceId: string): Promise<TaskDetail> {
  return unwrap(apiClient.get<{ data: TaskDetail }>(`/tasks/${encodeURIComponent(traceId)}`));
}

/** 历史事件回放（来自 agent_events 表） */
export async function getTraceEvents(traceId: string): Promise<TraceEventsData> {
  return unwrap(
    apiClient.get<{ data: TraceEventsData }>(`/tasks/${encodeURIComponent(traceId)}/events`)
  );
}

/** 提交任务 — 对应 POST /api/run_task */
export async function runTask(payload: RunTaskRequest): Promise<RunTaskResponse> {
  const response = await apiClient.post<RunTaskResponse>('/run_task', payload);
  return response.data;
}

/** 获取已注册的任务名列表 — 对应 GET /api/task_names */
export async function getTaskNames(): Promise<string[]> {
  return unwrap(apiClient.get<{ data: string[] }>('/task_names'));
}

/** 请求取消任务 — 对应 POST /api/cancel_task */
export async function cancelTask(payload: CancelTaskRequest): Promise<RunTaskResponse> {
  const response = await apiClient.post<RunTaskResponse>('/cancel_task', payload);
  return response.data;
}
