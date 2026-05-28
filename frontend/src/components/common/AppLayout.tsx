import { useEffect, useMemo } from 'react';
import { Button, Layout, Menu, Input, Space, Typography, theme, Dropdown } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
  PartitionOutlined,
  ToolOutlined,
  MonitorOutlined,
  HistoryOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  MoonOutlined,
  SunOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useDarkMode } from '@/hooks/useDarkMode';
import { useAuthStore } from '@/stores/authStore';

const { Header, Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: '/chat', icon: <MessageOutlined />, label: 'Chat' },
  { key: '/run-task', icon: <PlayCircleOutlined />, label: 'Run Task' },
  { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/tasks', icon: <UnorderedListOutlined />, label: 'Tasks' },
  { key: '/traces', icon: <PartitionOutlined />, label: 'Traces' },
  { key: '/skills', icon: <ToolOutlined />, label: 'Skills' },
  { key: '/system', icon: <MonitorOutlined />, label: 'System' },
  { key: '/runs', icon: <HistoryOutlined />, label: 'Runs' },
  { key: '/account', icon: <SettingOutlined />, label: 'Account' },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const [dark, setDark] = useDarkMode();
  const account = useAuthStore((s) => s.account);
  const logout = useAuthStore((s) => s.logout);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  useEffect(() => {
    if (!account) fetchMe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** 当前激活的菜单 — 用前缀匹配，避免详情页失活 */
  const selectedKey = useMemo(() => {
    const item = NAV_ITEMS.slice()
      .sort((a, b) => b.key.length - a.key.length)
      .find((it) => location.pathname === it.key || location.pathname.startsWith(`${it.key}/`));
    return item?.key ?? '/';
  }, [location.pathname]);

  const handleGlobalSearch = (value: string) => {
    const v = value.trim();
    if (!v) return;
    if (v.startsWith('Agent-') || v.startsWith('Task-')) {
      navigate(`/tasks/${encodeURIComponent(v)}`);
    } else {
      navigate(`/tasks?task_name=${encodeURIComponent(v)}`);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  const userMenuItems = [
    {
      key: 'account',
      icon: <SettingOutlined />,
      label: '账号管理',
      onClick: () => navigate('/account'),
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        style={{ background: token.colorBgContainer, borderRight: `1px solid ${token.colorBorderSecondary}` }}
      >
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            padding: '0 20px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <img src="/logo.svg" alt="TaskPilot" width={24} height={24} />
          <Typography.Title level={5} style={{ margin: '0 0 0 10px' }}>
            TaskPilot
          </Typography.Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          style={{ borderRight: 0, paddingTop: 8 }}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            paddingInline: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <Typography.Text type="secondary">
            从定时任务到 Agentic 执行 — Web Console v1
          </Typography.Text>
          <Space>
            <Button
              type="text"
              icon={dark ? <SunOutlined /> : <MoonOutlined />}
              onClick={() => setDark(!dark)}
              title={dark ? '切换亮色模式' : '切换暗色模式'}
            />
            <Input.Search
              placeholder="搜索 trace_id 或任务名"
              allowClear
              onSearch={handleGlobalSearch}
              style={{ width: 280 }}
            />
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Button type="text" icon={<UserOutlined />}>
                {account?.username ?? '...'}
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: token.colorBgLayout }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
