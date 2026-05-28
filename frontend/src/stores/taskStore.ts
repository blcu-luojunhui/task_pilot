import { create } from 'zustand';
import type { ListTasksParams, TaskSummary } from '@/api/types';
import { listTasks } from '@/api/tasks';

interface TaskStoreState {
  items: TaskSummary[];
  total: number;
  loading: boolean;
  params: ListTasksParams;

  fetch: (params?: ListTasksParams) => Promise<void>;
  setParams: (patch: Partial<ListTasksParams>) => void;
  reset: () => void;
}

const DEFAULT_PARAMS: ListTasksParams = {
  page: 1,
  page_size: 20,
};

export const useTaskStore = create<TaskStoreState>((set, get) => ({
  items: [],
  total: 0,
  loading: false,
  params: { ...DEFAULT_PARAMS },

  fetch: async (override?: ListTasksParams) => {
    const next = { ...get().params, ...(override ?? {}) };
    set({ loading: true, params: next });
    try {
      const data = await listTasks(next);
      set({ items: data.items, total: data.total, loading: false });
    } catch {
      // 拦截器已经弹了 message，这里只回滚 loading
      set({ loading: false });
    }
  },

  setParams: (patch) => {
    set((state) => ({ params: { ...state.params, ...patch } }));
  },

  reset: () => set({ items: [], total: 0, params: { ...DEFAULT_PARAMS } }),
}));
