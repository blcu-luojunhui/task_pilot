import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  login as apiLogin,
  register as apiRegister,
  logout as apiLogout,
  getMe,
  type AccountInfo,
} from '@/api/auth';

interface AuthState {
  token: string | null;
  account: AccountInfo | null;
  loading: boolean;
  /** 登录 */
  login: (username: string, password: string) => Promise<void>;
  /** 注册 */
  register: (username: string, email: string, password: string) => Promise<void>;
  /** 登出 */
  logout: () => Promise<void>;
  /** 刷新当前用户信息 */
  fetchMe: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      account: null,
      loading: false,

      login: async (username: string, password: string) => {
        set({ loading: true });
        try {
          const result = await apiLogin(username, password);
          set({ token: result.token, account: null, loading: false });
          // login 只返回部分字段，需要再 fetchMe 拿完整信息
          await get().fetchMe();
        } catch (e) {
          set({ loading: false });
          throw e;
        }
      },

      register: async (username: string, email: string, password: string) => {
        set({ loading: true });
        try {
          const result = await apiRegister(username, email, password);
          set({ token: result.token, account: null, loading: false });
          await get().fetchMe();
        } catch (e) {
          set({ loading: false });
          throw e;
        }
      },

      logout: async () => {
        try {
          await apiLogout();
        } catch {
          // ignore logout errors
        }
        set({ token: null, account: null });
      },

      fetchMe: async () => {
        try {
          const account = await getMe();
          set({ account });
        } catch {
          // 401 will be handled by interceptor
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    },
  ),
);
