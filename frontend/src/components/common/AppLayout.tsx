import { useEffect, useMemo } from 'react';
import { Button, Layout, Menu, Input, Space, Typography, theme, Dropdown } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
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
import { useTranslation } from 'react-i18next';
import { useDarkMode } from '@/hooks/useDarkMode';
import { useAuthStore } from '@/stores/authStore';
import { useLocaleStore } from '@/stores/localeStore';

const { Header, Sider, Content } = Layout;

const NAV_ITEMS = [
  { key: '/chat', icon: <MessageOutlined />, label: 'Chat' },
  { key: '/run-task', icon: <PlayCircleOutlined />, label: 'Run Task' },
  { key: '/', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/tasks', icon: <UnorderedListOutlined />, label: 'Tasks' },
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
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);
  const { t } = useTranslation('common');

  useEffect(() => {
    if (!account) fetchMe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
      label: t('app.userMenu.account'),
      onClick: () => navigate('/account'),
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: t('app.userMenu.logout'),
      onClick: handleLogout,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        style={{
          background: token.colorBgContainer,
          boxShadow: '1px 0 8px rgba(0,0,0,0.04)',
          borderRight: 'none',
          zIndex: 10,
        }}
      >
        <div
          className="sider-logo"
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            padding: '0 20px',
          }}
        >
          <img src="/logo.svg" alt="TaskPilot" width={28} height={28} />
          <span
            className="gradient-text"
            style={{
              marginLeft: 10,
              fontSize: 17,
              fontWeight: 700,
              letterSpacing: '-0.3px',
            }}
          >
            TaskPilot
          </span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          style={{ borderRight: 0, paddingTop: 4 }}
          items={NAV_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
            borderBottom: 'none',
            paddingInline: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            zIndex: 9,
            position: 'sticky',
            top: 0,
          }}
        >
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {t('app.subtitle')}
          </Typography.Text>
          <Space size={8}>
            <Button
              type="text"
              onClick={() => setLocale(locale === 'zh' ? 'en' : 'zh')}
              style={{ fontWeight: 600, fontSize: 12, minWidth: 36 }}
            >
              {locale === 'zh' ? 'EN' : '中'}
            </Button>
            <Button
              type="text"
              icon={dark ? <SunOutlined /> : <MoonOutlined />}
              onClick={() => setDark(!dark)}
              title={dark ? t('app.darkModeTooltipOn') : t('app.darkModeTooltipOff')}
            />
            <Input.Search
              placeholder={t('app.searchPlaceholder')}
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
        <Content style={{ padding: 24, background: token.colorBgLayout, minHeight: 'calc(100vh - 56px)' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
