import { lazy, Suspense, useEffect } from 'react';
import { ConfigProvider, App as AntApp, theme as antdTheme, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/common/AppLayout';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { PageLoader } from '@/components/common/PageLoader';
import { useDarkMode } from '@/hooks/useDarkMode';
import { useLocaleStore } from '@/stores/localeStore';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import '@/locales/i18n';
import { FONT_MONO, FONT_SANS } from '@/utils/fonts';

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
  const [dark] = useDarkMode();
  const locale = useLocaleStore((s) => s.locale);

  useEffect(() => {
    dayjs.locale(DAYJS_LOCALE_MAP[locale]);
  }, [locale]);

  // 代码高亮主题随亮/暗切换（FE-5）
  useEffect(() => {
    void (dark
      ? import('highlight.js/styles/github-dark.css')
      : import('highlight.js/styles/github.css'));
  }, [dark]);

  return (
    <ConfigProvider
      locale={ANTD_LOCALE_MAP[locale]}
      theme={{
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 8,
          fontFamily: FONT_SANS,
          fontFamilyCode: FONT_MONO,
          fontSize: 14,
          lineHeight: 1.6,
          controlHeight: 36,
          paddingContentHorizontal: 20,
          paddingContentVertical: 16,
          colorBorderSecondary: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
        },
        components: {
          Card: {
            borderRadiusLG: 10,
            paddingLG: 20,
          },
          Menu: {
            itemBorderRadius: 8,
            itemMarginInline: 8,
            itemHeight: 38,
            iconSize: 17,
          },
          Layout: {
            headerBg: dark ? '#141414' : '#ffffff',
            siderBg: dark ? '#141414' : '#fafafa',
            bodyBg: dark ? '#000000' : '#f5f5f5',
          },
          Button: {
            borderRadius: 8,
            controlHeight: 36,
            paddingInline: 16,
            contentFontSize: 14,
          },
          Input: {
            borderRadius: 8,
            controlHeight: 36,
          },
          Table: {
            borderRadiusLG: 10,
            headerBg: dark ? '#1d1d1d' : '#fafafa',
            headerBorderRadius: 10,
          },
          Segmented: {
            borderRadius: 8,
          },
          Select: {
            borderRadius: 8,
          },
          DatePicker: {
            borderRadius: 8,
          },
          Tag: {
            borderRadiusSM: 4,
          },
        },
      }}
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
