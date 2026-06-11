import { useEffect, useState, useCallback } from 'react';
import {
  Card,
  Descriptions,
  Button,
  Table,
  Modal,
  Input,
  Typography,
  Space,
  Tag,
  Popconfirm,
  message,
  Spin,
  Progress,
  Row,
  Col,
  Select,
  InputNumber,
  Statistic,
  theme,
} from 'antd';
import {
  PlusOutlined,
  KeyOutlined,
  CopyOutlined,
  UserOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import {
  type TokenInfo,
  type CreateTokenResult,
  type AdminUserInfo,
  createToken,
  listTokens,
  revokeToken,
  listUsers,
  updateUserRole,
  updateUserQuota,
} from '@/api/auth';
import { apiClient, unwrap } from '@/api/client';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';

const cardStyle: React.CSSProperties = { borderRadius: 10 };

export function AccountPage() {
  const { token: themeToken } = theme.useToken();
  const { t } = useTranslation('account');
  const account = useAuthStore((s) => s.account);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [loadingTokens, setLoadingTokens] = useState(false);
  const [newToken, setNewToken] = useState<CreateTokenResult | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [tokenName, setTokenName] = useState('');
  const [creating, setCreating] = useState(false);

  // admin
  const isAdmin = account?.role === 'admin';
  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usageRanking, setUsageRanking] = useState<Array<{ username: string; role: string; total_tokens: number }>>([]);
  const [loadingRanking, setLoadingRanking] = useState(false);

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;
    setLoadingUsers(true);
    try {
      const data = await listUsers();
      setUsers(data.items);
    } catch {
      // ignore
    } finally {
      setLoadingUsers(false);
    }
  }, [isAdmin]);

  const handleRoleChange = async (userId: number, role: string) => {
    try {
      await updateUserRole(userId, role);
      message.success(t('roleUpdated'));
      await loadUsers();
    } catch {
      // ignore
    }
  };

  const handleQuotaChange = async (userId: number, limit: number | null) => {
    if (limit == null) return;
    try {
      await updateUserQuota(userId, limit);
      message.success(t('quotaUpdated'));
      await loadUsers();
    } catch {
      // ignore
    }
  };

  const loadTokens = useCallback(async () => {
    setLoadingTokens(true);
    try {
      const list = await listTokens();
      setTokens(list);
    } catch {
      // handled by interceptor
    } finally {
      setLoadingTokens(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
    loadTokens();
  }, [fetchMe, loadTokens]);

  const loadRanking = useCallback(async () => {
    if (!isAdmin) return;
    setLoadingRanking(true);
    try {
      const data = await unwrap<{ days: number; ranking: typeof usageRanking }>(
        apiClient.get('/auth/admin/stats/usage', { params: { days: 7 } })
      );
      setUsageRanking(data.ranking);
    } catch {
      // ignore
    } finally {
      setLoadingRanking(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    if (isAdmin) {
      loadUsers();
      loadRanking();
    }
  }, [isAdmin, loadUsers, loadRanking]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const result = await createToken(tokenName || undefined);
      setNewToken(result);
      await loadTokens();
    } catch {
      // handled by interceptor
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (id: number) => {
    try {
      await revokeToken(id);
      message.success(t('tokenRevoked'));
      await loadTokens();
    } catch {
      // handled by interceptor
    }
  };

  const copyToken = (text: string) => {
    navigator.clipboard.writeText(text).then(
      () => message.success(t('copied')),
      () => message.warning(t('copyFailed')),
    );
  };

  const usagePercent = account?.daily_token_limit
    ? Math.round((account.today_tokens_used / account.daily_token_limit) * 100)
    : 0;

  const tokenColumns = [
    {
      title: t('columnPrefix'),
      dataIndex: 'token_prefix',
      key: 'token_prefix',
      render: (v: string) => <code>{v}...</code>,
    },
    {
      title: t('columnName'),
      dataIndex: 'name',
      key: 'name',
      render: (v: string | null) => v || <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: t('columnLastUsed'),
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm') : <Typography.Text type="secondary">{t('columnNeverUsed')}</Typography.Text>,
    },
    {
      title: t('columnExpires'),
      dataIndex: 'expires_at',
      key: 'expires_at',
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm') : <Tag color="green">{t('columnNeverExpires')}</Tag>,
    },
    {
      title: t('columnCreatedAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: t('columnActions'),
      key: 'actions',
      render: (_: unknown, record: TokenInfo) => (
        <Popconfirm
          title={t('revokeConfirm')}
          onConfirm={() => handleRevoke(record.id)}
          okText={t('revokeOk')}
          cancelText={t('revokeCancel')}
        >
          <Button size="small" danger type="link">
            {t('revoke')}
          </Button>
        </Popconfirm>
      ),
    },
  ];

  if (!account) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '8px 0 40px' }}>
      <div style={{ marginBottom: 24 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          <UserOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
          {t('title')}
        </Typography.Title>
        <Typography.Text type="secondary">{t('subtitle')}</Typography.Text>
      </div>

      {/* 基本信息 */}
      <Card
        variant="borderless"
        style={cardStyle}
        title={
          <span>
            <SafetyCertificateOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
            {t('basicInfo')}
          </span>
        }
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Descriptions column={2} size="small">
          <Descriptions.Item label={t('username')}>{account.username}</Descriptions.Item>
          <Descriptions.Item label={t('email')}>{account.email}</Descriptions.Item>
          <Descriptions.Item label={t('role')}>
            <Tag color={isAdmin ? 'red' : 'blue'}>{account.role}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('registeredAt')}>
            {dayjs(account.created_at).format('YYYY-MM-DD HH:mm')}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 用量 */}
      <Card
        variant="borderless"
        style={cardStyle}
        title={
          <span>
            <ThunderboltOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
            {t('todayUsage')}
          </span>
        }
        styles={{ body: { padding: '16px 24px' } }}
      >
        <Row gutter={32} align="middle">
          <Col xs={24} md={12}>
            <Progress
              percent={usagePercent}
              status={usagePercent >= 100 ? 'exception' : 'active'}
              format={() => `${account.today_tokens_used.toLocaleString()} / ${account.daily_token_limit.toLocaleString()}`}
              strokeColor={
                usagePercent >= 100
                  ? '#ff4d4f'
                  : usagePercent >= 80
                    ? '#faad14'
                    : themeToken.colorPrimary
              }
            />
          </Col>
          <Col xs={24} md={12}>
            <Row gutter={24}>
              <Col span={12}>
                <Statistic
                  title={t('used')}
                  value={account.today_tokens_used}
                  suffix="tokens"
                  valueStyle={{ fontSize: 20 }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title={t('dailyQuota')}
                  value={account.daily_token_limit}
                  suffix="tokens"
                  valueStyle={{ fontSize: 20 }}
                />
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>

      {/* Token 管理 */}
      <Card
        variant="borderless"
        style={cardStyle}
        title={
          <span>
            <KeyOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
            {t('tokens')}
          </span>
        }
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setNewToken(null);
              setTokenName('');
              setShowCreateModal(true);
            }}
          >
            {t('createToken')}
          </Button>
        }
        styles={{ body: { padding: 0 } }}
      >
        <Table
          dataSource={tokens}
          columns={tokenColumns}
          rowKey="id"
          loading={loadingTokens}
          pagination={false}
          size="middle"
        />
      </Card>

      {/* Admin: 用量排名 */}
      {isAdmin && (
        <Card
          variant="borderless"
          style={cardStyle}
          title={
            <span>
              <BarChartOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
              {t('rankingTitle')}
            </span>
          }
          loading={loadingRanking}
          styles={{ body: { padding: 0 } }}
        >
          <Table
            dataSource={usageRanking}
            rowKey="username"
            pagination={false}
            size="middle"
            columns={[
              { title: t('rankingUser'), dataIndex: 'username', key: 'username' },
              {
                title: t('rankingRole'),
                dataIndex: 'role',
                key: 'role',
                width: 80,
                render: (r: string) => <Tag color={r === 'admin' ? 'red' : 'blue'}>{r}</Tag>,
              },
              {
                title: t('rankingTokens'),
                dataIndex: 'total_tokens',
                key: 'total_tokens',
                render: (v: number) => v.toLocaleString(),
              },
            ]}
          />
        </Card>
      )}

      {/* Admin: 用户管理 */}
      {isAdmin && (
        <Card
          variant="borderless"
          style={cardStyle}
          title={
            <span>
              <TeamOutlined style={{ marginRight: 8, color: themeToken.colorPrimary }} />
              {t('adminUsers')}
            </span>
          }
          styles={{ body: { padding: 0 } }}
        >
          <Table
            dataSource={users}
            rowKey="id"
            loading={loadingUsers}
            pagination={false}
            size="middle"
            columns={[
              { title: t('adminId'), dataIndex: 'id', key: 'id', width: 60 },
              { title: t('adminUsername'), dataIndex: 'username', key: 'username' },
              { title: t('adminEmail'), dataIndex: 'email', key: 'email' },
              {
                title: t('adminRole'),
                dataIndex: 'role',
                key: 'role',
                width: 160,
                render: (role: string, record: AdminUserInfo) => (
                  <Select
                    size="small"
                    value={role}
                    style={{ width: 120 }}
                    disabled={record.id === account.id}
                    onChange={(value) => handleRoleChange(record.id, value)}
                    options={[
                      { label: 'admin', value: 'admin' },
                      { label: 'user', value: 'user' },
                    ]}
                  />
                ),
              },
              {
                title: t('adminQuota'),
                dataIndex: 'daily_token_limit',
                key: 'daily_token_limit',
                width: 140,
                render: (v: number, record: AdminUserInfo) => (
                  <InputNumber
                    size="small"
                    min={0}
                    value={v}
                    style={{ width: 120 }}
                    onPressEnter={() => handleQuotaChange(record.id, record.daily_token_limit)}
                    onBlur={(e) => {
                      const val = parseInt((e.target as HTMLInputElement).value, 10);
                      if (!isNaN(val) && val !== v) handleQuotaChange(record.id, val);
                    }}
                  />
                ),
              },
              {
                title: t('adminRegisteredAt'),
                dataIndex: 'created_at',
                key: 'created_at',
                render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
              },
            ]}
          />
        </Card>
      )}

      {/* 创建 Token 弹窗 */}
      <Modal
        title={t('createTokenModal')}
        open={showCreateModal}
        onCancel={() => setShowCreateModal(false)}
        footer={newToken ? [
          <Button key="close" onClick={() => setShowCreateModal(false)}>
            {t('close')}
          </Button>,
        ] : [
          <Button key="cancel" onClick={() => setShowCreateModal(false)}>
            {t('revokeCancel')}
          </Button>,
          <Button key="create" type="primary" loading={creating} onClick={handleCreate}>
            {t('create')}
          </Button>,
        ]}
      >
        {newToken ? (
          <div>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text strong>
                {t('tokenCreatedHint')}
              </Typography.Text>
              <Input.TextArea
                value={newToken.token}
                readOnly
                rows={2}
                style={{ fontFamily: 'monospace' }}
              />
              <Button
                icon={<CopyOutlined />}
                onClick={() => copyToken(newToken.token)}
              >
                {t('copyToken')}
              </Button>
            </Space>
          </div>
        ) : (
          <div>
            <Typography.Paragraph type="secondary">
              {t('tokenNameHint')}
            </Typography.Paragraph>
            <Input
              prefix={<KeyOutlined />}
              placeholder={t('tokenNamePlaceholder')}
              value={tokenName}
              onChange={(e) => setTokenName(e.target.value)}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
