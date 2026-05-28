import type { TraceEventType } from '@/api/types';

/** harness 层事件清单（用于过滤/分类） */
export const HARNESS_EVENT_TYPES: ReadonlySet<TraceEventType> = new Set<TraceEventType>([
  'run_start',
  'step_start',
  'think_start',
  'think_end',
  'act_start',
  'act_end',
  'step_end',
  'feedback_collected',
  'improvement_recorded',
  'run_end',
  'run_error',
  'run_stopped',
]);

/** task_scheduler 层事件清单 */
export const TASK_EVENT_TYPES: ReadonlySet<TraceEventType> = new Set<TraceEventType>([
  'task.accepted',
  'task.started',
  'task.finished',
  'task.cancel_requested',
]);

/** chat 层事件清单 */
export const CHAT_EVENT_TYPES: ReadonlySet<TraceEventType> = new Set<TraceEventType>([
  'chat.token_delta',
  'chat.tool_call_start',
  'chat.tool_call_end',
  'chat.tool_call_proposed',
  'chat.turn_paused',
  'chat.turn_end',
  'chat.turn_error',
  'chat.user_message',
]);

/** 终止类事件（看到这些后端会 close trace） */
export const TERMINAL_EVENT_TYPES: ReadonlySet<TraceEventType> = new Set<TraceEventType>([
  'run_end',
  'run_error',
  'run_stopped',
  'task.finished',
  'chat.turn_end',
  'chat.turn_error',
]);

export function isHarnessEvent(type: TraceEventType): boolean {
  return HARNESS_EVENT_TYPES.has(type);
}

export function isTaskEvent(type: TraceEventType): boolean {
  return TASK_EVENT_TYPES.has(type);
}

export function isTerminalEvent(type: TraceEventType): boolean {
  return TERMINAL_EVENT_TYPES.has(type);
}
