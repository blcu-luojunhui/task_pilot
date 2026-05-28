import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';
import { message } from 'antd';

/**
 * 全局 axios 实例
 *
 * 设计要点：
 * - baseURL 用相对路径，开发期 Vite proxy 转发 /api，生产期 Quart 同源托管
 * - 请求拦截器自动携带 Bearer Token
 * - 响应拦截器统一拆 `{ code, message, data }` 包装，code !== 0 抛出错误
 * - 错误用 antd message 浅提示（避免每页重复处理），同时 throw 让组件可选择性 catch
 * - 401 自动登出
 */

export interface BackendError extends Error {
  code?: number;
  trace_id?: string;
  raw?: unknown;
}

function makeBackendError(rawCode: number, rawMessage: string, raw: unknown): BackendError {
  const err = new Error(rawMessage || `Backend error (code=${rawCode})`) as BackendError;
  err.code = rawCode;
  err.raw = raw;
  return err;
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截器：自动携带 Bearer Token
apiClient.interceptors.request.use((config) => {
  // 延迟导入避免循环依赖
  try {
    const stored = localStorage.getItem('auth-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      const token = parsed?.state?.token;
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
  } catch {
    // ignore parse errors
  }
  return config;
});

apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const body = response.data;
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      const err = makeBackendError(body.code, body.message ?? '', body);
      message.warning(err.message);
      return Promise.reject(err);
    }
    return response;
  },
  (error: AxiosError) => {
    // 401 自动清除登录态
    if (error.response?.status === 401) {
      localStorage.removeItem('auth-storage');
      // 不在登录页才跳转，避免死循环
      if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }
    if (error.response?.data) {
      const body = error.response.data as { code?: number; message?: string };
      const err = makeBackendError(body.code ?? -1, body.message ?? error.message, body);
      message.error(err.message);
      return Promise.reject(err);
    }
    if (error.code === 'ECONNABORTED') {
      message.error('请求超时，请检查后端服务');
    } else {
      message.error(`网络错误: ${error.message}`);
    }
    return Promise.reject(error);
  }
);

/** 拆 `{code, message, data}` 包装，返回 data */
export async function unwrap<T>(promise: Promise<AxiosResponse<{ data: T }>>): Promise<T> {
  const response = await promise;
  return response.data.data;
}
