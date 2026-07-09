import { lazy, Suspense, useEffect } from 'react';
import { ConfigProvider, App as AntApp, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/common/AppLayout';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { PageLoader } from '@/components/common/PageLoader';
import { useLocaleStore } from '@/stores/localeStore';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import '@/locales/i18n';
import { createAntdThemeConfig } from '@/theme/tokens';

const LoginPage = lazy(() => import('@/pages/LoginPage').then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() =>
  import('@/pages/RegisterPage').then((m) => ({ default: m.RegisterPage })),
);
const ChatPage = lazy(() => import('@/pages/ChatPage').then((m) => ({ default: m.ChatPage })));
const DashboardPage = lazy(() =>
  import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const AccountPage = lazy(() =>
  import('@/pages/AccountPage').then((m) => ({ default: m.AccountPage })),
);
const TasksPage = lazy(() => import('@/pages/TasksPage').then((m) => ({ default: m.TasksPage })));
const TaskDetailPage = lazy(() =>
  import('@/pages/TaskDetailPage').then((m) => ({ default: m.TaskDetailPage })),
);
const SkillsPage = lazy(() => import('@/pages/SkillsPage').then((m) => ({ default: m.SkillsPage })));
const SystemPage = lazy(() => import('@/pages/SystemPage').then((m) => ({ default: m.SystemPage })));
const RunsPage = lazy(() => import('@/pages/RunsPage').then((m) => ({ default: m.RunsPage })));
const RunTaskPage = lazy(() =>
  import('@/pages/RunTaskPage').then((m) => ({ default: m.RunTaskPage })),
);
const EvalsPage = lazy(() =>
  import('@/pages/EvalsPage').then((m) => ({ default: m.EvalsPage })),
);

const ANTD_LOCALE_MAP = { zh: zhCN, en: enUS };
const DAYJS_LOCALE_MAP: Record<string, string> = { zh: 'zh-cn', en: 'en' };

function RouteFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
      <Spin size="large" />
    </div>
  );
}

export function App() {
  const locale = useLocaleStore((s) => s.locale);

  useEffect(() => {
    dayjs.locale(DAYJS_LOCALE_MAP[locale]);
  }, [locale]);

  // 代码高亮主题
  useEffect(() => {
    void import('highlight.js/styles/github.css');
  }, []);

  return (
    <ConfigProvider
      locale={ANTD_LOCALE_MAP[locale]}
      theme={createAntdThemeConfig(false)}
    >
      <AntApp>
        <ErrorBoundary>
          <BrowserRouter>
            <Suspense fallback={<RouteFallback />}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route
                  element={
                    <RequireAuth>
                      <AppLayout />
                    </RequireAuth>
                  }
                >
                  <Route
                    path="/chat"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <ChatPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <DashboardPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/account"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <AccountPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/tasks"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <TasksPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/tasks/:traceId"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <TaskDetailPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/skills"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <SkillsPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/system"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <SystemPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/runs"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <RunsPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/evals"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <EvalsPage />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/run-task"
                    element={
                      <Suspense fallback={<PageLoader />}>
                        <RunTaskPage />
                      </Suspense>
                    }
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
