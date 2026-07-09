import { create } from 'zustand';
import type { TraceEvent } from '@/api/types';
import { getTraceEvents } from '@/api/tasks';

/**
 * Trace store —— 当前打开的单个 trace 的事件流
 *
 * 设计：
 * - 一次只承载一个活跃 trace（切换路由强制 reset）
 * - appendEvent 走增量（用于未来 SSE 接入）
 * - 用 sequence 去重，保证 history + live 拼接时不出现重复
 */

interface TraceStoreState {
  traceId: string | null;
  events: TraceEvent[];
  closed: boolean;
  loading: boolean;
  frozen: boolean;

  open: (traceId: string) => Promise<void>;
  appendEvent: (event: TraceEvent) => void;
  setFrozen: (frozen: boolean) => void;
  reset: () => void;
}

export const useTraceStore = create<TraceStoreState>((set, get) => ({
  traceId: null,
  events: [],
  closed: false,
  loading: false,
  frozen: false,

  open: async (traceId: string) => {
    if (get().traceId === traceId && get().events.length > 0) return;
    set({ traceId, events: [], closed: false, frozen: false, loading: true });
    try {
      const data = await getTraceEvents(traceId);
      set({ events: data.events, closed: data.closed, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  appendEvent: (event: TraceEvent) => {
    set((state) => {
      if (state.frozen) return state;
      if (state.traceId !== event.trace_id) return state;
      if (state.events.some((e) => e.sequence === event.sequence)) return state;
      return { events: [...state.events, event].sort((a, b) => a.sequence - b.sequence) };
    });
  },

  setFrozen: (frozen: boolean) => set({ frozen }),

  reset: () => set({ traceId: null, events: [], closed: false, loading: false, frozen: false }),
}));
