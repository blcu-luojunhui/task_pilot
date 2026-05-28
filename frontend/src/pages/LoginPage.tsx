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
import { useAuthStore } from '@/stores/authStore';

export function LoginPage() {
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
      <Card style={{ width: 400 }} bordered={false}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>
            TaskPilot
          </Typography.Title>
          <Typography.Text type="secondary">登录到控制台</Typography.Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} size="large">
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 12 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Space>
            <Typography.Text type="secondary">没有账号？</Typography.Text>
            <Link to="/register">立即注册</Link>
          </Space>
        </div>
      </Card>
    </div>
  );
}
