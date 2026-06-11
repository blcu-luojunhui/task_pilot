import { create } from 'zustand';
import type { ListTasksParams, TaskSummary } from '@/api/types';
import { listTasks, listAdminTasks } from '@/api/tasks';

interface TaskStoreState {
  items: TaskSummary[];
  total: number;
  loading: boolean;
  adminMode: boolean;
  params: ListTasksParams;

  fetch: (params?: ListTasksParams) => Promise<void>;
  setAdminMode: (mode: boolean) => void;
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
  adminMode: false,
  params: { ...DEFAULT_PARAMS },

  fetch: async (override?: ListTasksParams) => {
    const { params, adminMode } = get();
    const next = { ...params, ...(override ?? {}) };
    set({ loading: true, params: next });
    try {
      const fetcher = adminMode ? listAdminTasks : listTasks;
      const data = await fetcher(next);
      set({ items: data.items, total: data.total, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setAdminMode: (mode: boolean) => {
    if (mode !== get().adminMode) {
      set({ adminMode: mode, items: [], total: 0, params: { ...DEFAULT_PARAMS } });
    }
  },

  setParams: (patch) => {
    set((state) => ({ params: { ...state.params, ...patch } }));
  },

  reset: () => set({ items: [], total: 0, params: { ...DEFAULT_PARAMS } }),
}));
