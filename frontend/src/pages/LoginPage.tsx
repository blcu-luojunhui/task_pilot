import { useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  Typography,
  Space,
  theme,
} from 'antd';
import { UserOutlined, LockOutlined, GithubOutlined } from '@ant-design/icons';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
export function LoginPage() {
  const { t } = useTranslation('auth');
  const [loading, setLoading] = useState(false);
  const token = useAuthStore((s) => s.token);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();
  const { token: themeToken } = theme.useToken();

  if (token) {
    return <Navigate to="/chat" replace />;
  }

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      navigate('/chat', { replace: true });
    } catch (err) {
      console.error('Login failed', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: themeToken.colorBgLayout,
      }}
    >
      <Card
        style={{ width: 400, borderRadius: 14, boxShadow: 'none' }}
        bordered={false}
      >
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            <span style={{ color: "var(--n0)" }}>TaskPilot</span>
          </Typography.Title>
          <Typography.Text type="secondary">{t('login.subtitle')}</Typography.Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} size="large">
          <Form.Item
            name="username"
            rules={[{ required: true, message: t('login.usernameRequired') }]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('login.usernamePlaceholder')} autoFocus />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: t('login.passwordRequired') }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('login.passwordPlaceholder')} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block size="large"
              style={{ background: 'var(--n0)', border: 'none' }}
            >
              {t('login.submitButton')}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Space>
            <Typography.Text type="secondary">{t('login.noAccount')}</Typography.Text>
            <Link to="/register">{t('login.registerLink')}</Link>
          </Space>
        </div>

        <div style={{ textAlign: 'center', marginTop: 20, paddingTop: 20, borderTop: `1px solid ${themeToken.colorBorderSecondary}` }}>
          <a
            href="https://github.com/blcu-luojunhui/task_pilot"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--n2)', fontSize: 17 }}
          >
            <GithubOutlined style={{ marginRight: 8, fontSize: 17 }} />
            TaskPilot on GitHub
          </a>
        </div>
      </Card>
    </div>
  );
}
