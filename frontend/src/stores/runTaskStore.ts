import { create } from 'zustand';
import { runAgentGoal, listToolAreas, type RunAgentResponse } from '@/api/agent';
import type { TraceEvent, ToolCall } from '@/api/types';
import { apiClient } from '@/api/client';

export interface ToolCallStatus {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'completed' | 'failed';
  result?: unknown;
}

export interface PendingPlan {
  toolCalls: ToolCall[];
  traceId: string;
}

interface RunTaskState {
  // 配置
  toolAreas: string[];
  selectedAreas: string[];
  goal: string;

  // 运行状态
  traceId: string | null;
  inFlight: boolean;
  streamingText: string;
  toolCalls: ToolCallStatus[];
  pendingPlan: PendingPlan | null;
  finalResult: string | null;
  error: string | null;

  // 操作
  fetchToolAreas: () => Promise<void>;
  setGoal: (goal: string) => void;
  toggleArea: (area: string) => void;
  run: () => Promise<string | null>;
  confirmPlan: (action: 'confirm' | 'reject') => Promise<void>;
  cancel: () => Promise<void>;
  handleLiveEvent: (event: TraceEvent) => void;
  reset: () => void;
}

export const useRunTaskStore = create<RunTaskState>((set, get) => ({
  toolAreas: [],
  selectedAreas: ['chat_ops', 'task'],
  goal: '',

  traceId: null,
  inFlight: false,
  streamingText: '',
  toolCalls: [],
  pendingPlan: null,
  finalResult: null,
  error: null,

  fetchToolAreas: async () => {
    try {
      const data = await listToolAreas();
      set({ toolAreas: data.tool_areas });
    } catch {
      // 默认列表兜底
      set({ toolAreas: ['chat_ops', 'database', 'http', 'task', 'utils'] });
    }
  },

  setGoal: (goal) => set({ goal }),

  toggleArea: (area) =>
    set((s) => ({
      selectedAreas: s.selectedAreas.includes(area)
        ? s.selectedAreas.filter((a) => a !== area)
        : [...s.selectedAreas, area],
    })),

  run: async () => {
    const { goal, selectedAreas } = get();
    if (!goal.trim()) return null;

    set({
      inFlight: true,
      streamingText: '',
      toolCalls: [],
      pendingPlan: null,
      finalResult: null,
      error: null,
    });

    try {
      const resp: RunAgentResponse = await runAgentGoal(goal.trim(), selectedAreas);
      set({ traceId: resp.trace_id });
      return resp.trace_id;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'run failed';
      set({ inFlight: false, error: msg });
      return null;
    }
  },

  confirmPlan: async (_action) => {
    // 暂不支持 plan confirm，ChatTurnRunner 的 pending_confirmation 需要特殊处理
    // 后续可通过 agent/confirm 端点实现
    set({ pendingPlan: null });
  },

  cancel: async () => {
    const { traceId } = get();
    if (!traceId) return;
    try {
      await apiClient.post('/cancel_task', { trace_id: traceId });
    } catch {
      // 后端 message 提示
    }
    set({ inFlight: false });
  },

  handleLiveEvent: (event: TraceEvent) => {
    const data = event.data ?? {};

    switch (event.type) {
      case 'chat.token_delta': {
        const delta = (data.delta as string) ?? '';
        if (delta) {
          set((s) => ({ streamingText: s.streamingText + delta }));
        } else {
          const acc = (data.accumulated as string) ?? '';
          if (acc) set({ streamingText: acc });
        }
        break;
      }

      case 'chat.tool_call_start': {
        const callId = (data.call_id as string) ?? '';
        const toolName = (data.tool_name as string) ?? '';
        const args = (data.arguments as Record<string, unknown>) ?? {};
        set((s) => ({
          toolCalls: [
            ...s.toolCalls,
            { callId, toolName, arguments: args, status: 'running' as const },
          ],
        }));
        break;
      }

      case 'chat.tool_call_end': {
        const callId = (data.call_id as string) ?? '';
        const ok = (data.ok as boolean) ?? false;
        const result = data.result;
        set((s) => ({
          toolCalls: s.toolCalls.map((tc) =>
            tc.callId === callId
              ? {
                  ...tc,
                  status: ok ? ('completed' as const) : ('failed' as const),
                  result,
                }
              : tc,
          ),
        }));
        break;
      }

      case 'chat.tool_call_proposed': {
        const tcs = (data.tool_calls as ToolCall[]) ?? [];
        set({
          pendingPlan: {
            toolCalls: tcs,
            traceId: event.trace_id ?? '',
          },
        });
        break;
      }

      case 'chat.turn_paused': {
        set({ inFlight: false });
        break;
      }

      case 'chat.turn_end': {
        const content = (data.content as string) ?? '';
        set({
          finalResult: content,
          inFlight: false,
          traceId: null,
        });
        break;
      }

      case 'chat.turn_error': {
        set({
          error: (data.error as string) ?? 'agent execution error',
          inFlight: false,
          traceId: null,
        });
        break;
      }

      case 'task.finished': {
        set({
          inFlight: false,
          traceId: null,
        });
        break;
      }

      default:
        break;
    }
  },

  reset: () =>
    set({
      traceId: null,
      inFlight: false,
      streamingText: '',
      toolCalls: [],
      pendingPlan: null,
      finalResult: null,
      error: null,
    }),
}));
