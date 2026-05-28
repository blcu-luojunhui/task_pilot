import { ConfigProvider, App as AntApp, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
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
import { TracesPage } from '@/pages/TracesPage';
import { SkillsPage } from '@/pages/SkillsPage';
import { SystemPage } from '@/pages/SystemPage';
import { RunsPage } from '@/pages/RunsPage';
import { RunTaskPage } from '@/pages/RunTaskPage';
import { useDarkMode } from '@/hooks/useDarkMode';

export function App() {
  const [dark] = useDarkMode();

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
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
                <Route path="/traces" element={<TracesPage />} />
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
