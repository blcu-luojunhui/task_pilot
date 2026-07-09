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
import { UserOutlined, LockOutlined, MailOutlined, KeyOutlined, GithubOutlined } from '@ant-design/icons';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';

export function RegisterPage() {
  const { t } = useTranslation('auth');
  const [loading, setLoading] = useState(false);
  const token = useAuthStore((s) => s.token);
  const register = useAuthStore((s) => s.register);
  const navigate = useNavigate();
  const { token: themeToken } = theme.useToken();

  if (token) {
    return <Navigate to="/chat" replace />;
  }

  const onFinish = async (values: {
    username: string;
    email: string;
    password: string;
    passwordConfirm: string;
    inviteCode?: string;
  }) => {
    setLoading(true);
    try {
      await register(values.username, values.email, values.password, values.inviteCode);
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
        background: themeToken.colorBgLayout,
      }}
    >
      <Card style={{ width: 420, borderRadius: 14, boxShadow: '0 4px 24px rgba(0,0,0,0.08)' }} bordered={false}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            <span style={{ color: "var(--n0)" }}>TaskPilot</span>
          </Typography.Title>
          <Typography.Text type="secondary">{t('register.subtitle')}</Typography.Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} size="large">
          <Form.Item
            name="username"
            rules={[
              { required: true, message: t('register.usernameRequired') },
              { min: 2, max: 64, message: t('register.usernameLength') },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder={t('register.usernamePlaceholder')} autoFocus />
          </Form.Item>

          <Form.Item
            name="email"
            validateTrigger="onBlur"
            rules={[
              { required: true, message: t('register.emailRequired') },
              { type: 'email', message: t('register.emailInvalid') },
              {
                validator: (_, value: string) => {
                  if (!value || !value.includes('@')) return Promise.resolve();
                  const allowed = [
                    'qq.com', '163.com', '126.com', 'gmail.com', 'outlook.com',
                    'hotmail.com', 'live.com', 'sina.com', 'sohu.com', 'yeah.net',
                    'foxmail.com', 'proton.me', 'protonmail.com', 'icloud.com',
                    'yahoo.com', 'zoho.com', 'aliyun.com',
                  ];
                  const domain = value.split('@')[1]?.toLowerCase();
                  if (!domain || !allowed.includes(domain)) {
                    return Promise.reject(new Error(t('register.emailDomainNotAllowed')));
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder={t('register.emailPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: t('register.passwordRequired') },
              { min: 6, message: t('register.passwordMin') },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('register.passwordPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="passwordConfirm"
            dependencies={['password']}
            rules={[
              { required: true, message: t('register.confirmRequired') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('register.passwordMismatch')));
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder={t('register.confirmPasswordPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="inviteCode"
            rules={[
              { required: true, message: t('register.inviteCodeRequired') },
            ]}
          >
            <Input prefix={<KeyOutlined />} placeholder={t('register.inviteCodePlaceholder')} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block size="large"
              style={{ background: 'var(--n0)', border: 'none' }}
            >
              {t('register.submitButton')}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Space>
            <Typography.Text type="secondary">{t('register.hasAccount')}</Typography.Text>
            <Link to="/login">{t('register.loginLink')}</Link>
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
