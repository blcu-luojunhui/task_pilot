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
import { UserOutlined, LockOutlined } from '@ant-design/icons';
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
    } catch {
      // error handled by axios interceptor
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
        background: `linear-gradient(135deg, ${themeToken.colorPrimaryBg} 0%, ${themeToken.colorBgLayout} 100%)`,
      }}
    >
      <Card
        style={{ width: 400, borderRadius: 14, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }}
        bordered={false}
      >
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            <span className="gradient-text">TaskPilot</span>
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
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
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
      </Card>
    </div>
  );
}
