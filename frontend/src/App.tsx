import { useEffect } from 'react';
import { ConfigProvider, App as AntApp, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/common/AppLayout';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { LoginPage } from '@/pages/LoginPage';
import { RegisterPage } from '@/pages/RegisterPage';
import { AccountPage } from '@/pages/AccountPage';
import { ChatPage } from '@/pages/ChatPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { TasksPage } from '@/pages/TasksPage';
import { TaskDetailPage } from '@/pages/TaskDetailPage';
import { SkillsPage } from '@/pages/SkillsPage';
import { SystemPage } from '@/pages/SystemPage';
import { RunsPage } from '@/pages/RunsPage';
import { RunTaskPage } from '@/pages/RunTaskPage';
import { useDarkMode } from '@/hooks/useDarkMode';
import { useLocaleStore } from '@/stores/localeStore';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import '@/locales/i18n';

const ANTD_LOCALE_MAP = { zh: zhCN, en: enUS };
const DAYJS_LOCALE_MAP: Record<string, string> = { zh: 'zh-cn', en: 'en' };

export function App() {
  const [dark] = useDarkMode();
  const locale = useLocaleStore((s) => s.locale);

  useEffect(() => {
    dayjs.locale(DAYJS_LOCALE_MAP[locale]);
  }, [locale]);

  return (
    <ConfigProvider
      locale={ANTD_LOCALE_MAP[locale]}
      theme={{
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 8,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
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
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/" element={<DashboardPage />} />
                <Route path="/account" element={<AccountPage />} />
                <Route path="/tasks" element={<TasksPage />} />
                <Route path="/tasks/:traceId" element={<TaskDetailPage />} />
                <Route path="/skills" element={<SkillsPage />} />
                <Route path="/system" element={<SystemPage />} />
                <Route path="/runs" element={<RunsPage />} />
                <Route path="/run-task" element={<RunTaskPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
