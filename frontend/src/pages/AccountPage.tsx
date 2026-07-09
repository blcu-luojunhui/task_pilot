import { useEffect, useState, useCallback } from 'react';
import {
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
  Tabs,
  theme,
} from 'antd';
import { useSemanticColors } from '@/hooks/useSemanticColors';
import {
  PlusOutlined,
  KeyOutlined,
  CopyOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  BarChartOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import {
  type TokenInfo,
  type CreateTokenResult,
  type AdminUserInfo,
  type InviteCodeInfo,
  type CreateInviteCodesResult,
  createToken,
  listTokens,
  revokeToken,
  listUsers,
  updateUserRole,
  updateUserQuota,
  createInviteCodes,
  listInviteCodes,
} from '@/api/auth';
import { apiClient, unwrap } from '@/api/client';
import { useTranslation } from 'react-i18next';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle, PageInfoItem } from '@/components/common/PageCard';
import { FONT_MONO } from '@/utils/fonts';
import dayjs from 'dayjs';

export function AccountPage() {
  const { token: themeToken } = theme.useToken();
  const palette = useSemanticColors();
  const { t } = useTranslation('account');
  const account = useAuthStore((s) => s.account);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [loadingTokens, setLoadingTokens] = useState(false);
  const [newToken, setNewToken] = useState<CreateTokenResult | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [tokenName, setTokenName] = useState('');
  const [creating, setCreating] = useState(false);

  const isAdmin = account?.role === 'admin';
  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usageRanking, setUsageRanking] = useState<Array<{ username: string; role: string; total_tokens: number }>>([]);
  const [loadingRanking, setLoadingRanking] = useState(false);

  const [inviteCodes, setInviteCodes] = useState<InviteCodeInfo[]>([]);
  const [loadingInviteCodes, setLoadingInviteCodes] = useState(false);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteCount, setInviteCount] = useState(1);
  const [newInviteCodes, setNewInviteCodes] = useState<CreateInviteCodesResult | null>(null);
  const [creatingInvite, setCreatingInvite] = useState(false);
  const [manualCodes, setManualCodes] = useState('');

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
        apiClient.get('/auth/admin/stats/usage', { params: { days: 7 } }),
      );
      setUsageRanking(data.ranking);
    } catch {
      // ignore
    } finally {
      setLoadingRanking(false);
    }
  }, [isAdmin]);

  const loadInviteCodes = useCallback(async () => {
    if (!isAdmin) return;
    setLoadingInviteCodes(true);
    try {
      const data = await listInviteCodes();
      setInviteCodes(data.items);
    } catch {
      // ignore
    } finally {
      setLoadingInviteCodes(false);
    }
  }, [isAdmin]);

  const handleCreateInviteCodes = async (mode: 'random' | 'manual') => {
    setCreatingInvite(true);
    try {
      let result: CreateInviteCodesResult;
      if (mode === 'manual') {
        const codes = manualCodes
          .split(/[\n,]+/)
          .map((s) => s.trim())
          .filter(Boolean);
        if (codes.length === 0) {
          message.warning(t('manualCodesEmpty'));
          setCreatingInvite(false);
          return;
        }
        result = await createInviteCodes({ codes });
      } else {
        result = await createInviteCodes({ count: inviteCount });
      }
      setNewInviteCodes(result);
      message.success(`已生成 ${result.count} 个邀请码`);
      await loadInviteCodes();
    } catch {
      // handled by interceptor
    } finally {
      setCreatingInvite(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadUsers();
      loadRanking();
      loadInviteCodes();
    }
  }, [isAdmin, loadUsers, loadRanking, loadInviteCodes]);

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

  const usageStroke =
    usagePercent >= 100
      ? palette.chartError
      : usagePercent >= 80
        ? palette.chartWarning
        : 'var(--color-accent)';

  const tokenColumns = [
    {
      title: t('columnPrefix'),
      dataIndex: 'token_prefix',
      key: 'token_prefix',
      render: (v: string) => (
        <code style={{ fontSize: 13, padding: '2px 8px', borderRadius: 6, background: themeToken.colorFillQuaternary }}>
          {v}...
        </code>
      ),
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
        v ? dayjs(v).format('YYYY-MM-DD HH:mm') : <Tag color="success">{t('columnNeverExpires')}</Tag>,
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
      width: 90,
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
    <PageShell>
      <PageHero
        title={t('title')}
        subtitle={t('subtitle')}
        avatarText={account.username}
        gradient="blue"
        extra={
          <Tag
            color={isAdmin ? 'red' : 'blue'}
            style={{ borderRadius: 20, padding: '4px 14px', fontSize: 13, fontWeight: 500, margin: 0 }}
          >
            {account.role}
          </Tag>
        }
      />

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={12}>
          <PageCard
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color={themeToken.colorPrimary} bg={themeToken.colorPrimaryBg}>
                    <SafetyCertificateOutlined />
                  </PageCardIcon>
                }
              >
                {t('basicInfo')}
              </PageCardTitle>
            }
            styles={{ body: { padding: '22px 24px' } }}
          >
            <div className="page-info-grid">
              <PageInfoItem label={t('username')} value={account.username} />
              <PageInfoItem label={t('email')} value={account.email} />
              <PageInfoItem
                label={t('role')}
                value={<Tag color={isAdmin ? 'red' : 'blue'}>{account.role}</Tag>}
              />
              <PageInfoItem
                label={t('registeredAt')}
                value={dayjs(account.created_at).format('YYYY-MM-DD HH:mm')}
              />
            </div>
          </PageCard>
        </Col>

        <Col xs={24} xl={12}>
          <PageCard
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color="#B45309" bg="rgba(180,83,9,0.06)">
                    <ThunderboltOutlined />
                  </PageCardIcon>
                }
              >
                {t('todayUsage')}
              </PageCardTitle>
            }
            styles={{ body: { padding: '22px 24px' } }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 28, flexWrap: 'wrap' }}>
              <Progress
                type="circle"
                percent={usagePercent}
                size={120}
                strokeWidth={8}
                strokeColor={usageStroke}
                format={() => (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.03em' }}>
                      {usagePercent}%
                    </div>
                    <div style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>used</div>
                  </div>
                )}
              />
              <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
                <div>
                  <div className="page-info-item__label">{t('used')}</div>
                  <div style={{ fontSize: 22, fontWeight: 600, color: usageStroke }}>
                    {account.today_tokens_used.toLocaleString()}
                  </div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>tokens</Typography.Text>
                </div>
                <div>
                  <div className="page-info-item__label">{t('dailyQuota')}</div>
                  <div style={{ fontSize: 22, fontWeight: 600 }}>
                    {account.daily_token_limit.toLocaleString()}
                  </div>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>tokens</Typography.Text>
                </div>
              </div>
            </div>
          </PageCard>
        </Col>

        <Col span={24}>
          <PageCard
            table
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color="#404040" bg="rgba(0,0,0,0.04)">
                    <KeyOutlined />
                  </PageCardIcon>
                }
              >
                {t('tokens')}
              </PageCardTitle>
            }
            extra={
              <Button
                type="primary"
                icon={<PlusOutlined />}
                style={{ borderRadius: 10, background: 'var(--color-accent)', boxShadow: 'none' }}
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
          </PageCard>
        </Col>

        {isAdmin && (
          <Col xs={24} xl={12}>
            <PageCard
              table
              title={
                <PageCardTitle
                  icon={
                    <PageCardIcon color="var(--n2)" bg="rgba(23,23,23,0.06)">
                      <BarChartOutlined />
                    </PageCardIcon>
                  }
                >
                  {t('rankingTitle')}
                </PageCardTitle>
              }
              loading={loadingRanking}
              styles={{ body: { padding: 0 } }}
            >
              <Table
                dataSource={usageRanking}
                rowKey="username"
                pagination={false}
                size="middle"
                locale={{ emptyText: t('rankingEmpty', { defaultValue: 'No usage data yet' }) }}
                columns={[
                  { title: t('rankingUser'), dataIndex: 'username', key: 'username' },
                  {
                    title: t('rankingRole'),
                    dataIndex: 'role',
                    key: 'role',
                    width: 90,
                    render: (r: string) => <Tag color={r === 'admin' ? 'red' : 'blue'}>{r}</Tag>,
                  },
                  {
                    title: t('rankingTokens'),
                    dataIndex: 'total_tokens',
                    key: 'total_tokens',
                    render: (v: number) => (
                      <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                        {v.toLocaleString()}
                      </span>
                    ),
                  },
                ]}
              />
            </PageCard>
          </Col>
        )}

        {isAdmin && (
          <Col xs={24} xl={12}>
            <PageCard
              table
              title={
                <PageCardTitle
                  icon={
                    <PageCardIcon color={themeToken.colorPrimary} bg={themeToken.colorPrimaryBg}>
                      <TeamOutlined />
                    </PageCardIcon>
                  }
                >
                  {t('adminUsers')}
                </PageCardTitle>
              }
              styles={{ body: { padding: 0 } }}
            >
              <Table
                dataSource={users}
                rowKey="id"
                loading={loadingUsers}
                pagination={false}
                size="middle"
                scroll={{ x: 720 }}
                columns={[
                  { title: t('adminId'), dataIndex: 'id', key: 'id', width: 60 },
                  { title: t('adminUsername'), dataIndex: 'username', key: 'username' },
                  { title: t('adminEmail'), dataIndex: 'email', key: 'email', ellipsis: true },
                  {
                    title: t('adminRole'),
                    dataIndex: 'role',
                    key: 'role',
                    width: 140,
                    render: (role: string, record: AdminUserInfo) => (
                      <Select
                        size="small"
                        value={role}
                        style={{ width: 110 }}
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
                    width: 130,
                    render: (v: number, record: AdminUserInfo) => (
                      <InputNumber
                        size="small"
                        min={0}
                        value={v}
                        style={{ width: 110 }}
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
                    width: 150,
                    render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
                  },
                ]}
              />
            </PageCard>
          </Col>
        )}

        {isAdmin && (
          <Col span={24}>
            <PageCard
              table
              title={
                <PageCardTitle
                  icon={
                    <PageCardIcon color="#B45309" bg="rgba(180,83,9,0.06)">
                      <SendOutlined />
                    </PageCardIcon>
                  }
                >
                  {t('inviteCodes')}
                </PageCardTitle>
              }
              extra={
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  style={{ borderRadius: 10, background: 'var(--color-warning)', boxShadow: 'none' }}
                  onClick={() => {
                    setNewInviteCodes(null);
                    setInviteCount(1);
                    setManualCodes('');
                    setShowInviteModal(true);
                  }}
                >
                  {t('generateInvite')}
                </Button>
              }
              styles={{ body: { padding: 0 } }}
            >
              <Table
                dataSource={inviteCodes}
                rowKey="id"
                loading={loadingInviteCodes}
                pagination={false}
                size="middle"
                scroll={{ x: 640 }}
                columns={[
                  {
                    title: t('inviteCode'),
                    dataIndex: 'code',
                    key: 'code',
                    width: 140,
                    render: (v: string) => (
                      <code style={{ fontSize: 13, padding: '2px 8px', borderRadius: 6, background: themeToken.colorFillQuaternary }}>
                        {v}
                      </code>
                    ),
                  },
                  { title: t('inviteCreatedBy'), dataIndex: 'created_by_name', key: 'created_by_name', width: 120 },
                  {
                    title: t('inviteStatus'),
                    dataIndex: 'status',
                    key: 'status',
                    width: 100,
                    render: (s: number) =>
                      s === 0 ? <Tag color="blue">{t('inviteUnused')}</Tag> : <Tag color="default">{t('inviteUsed')}</Tag>,
                  },
                  {
                    title: t('inviteUsedBy'),
                    dataIndex: 'used_by',
                    key: 'used_by',
                    width: 100,
                    render: (v: number | null) => (v != null ? v : '—'),
                  },
                  {
                    title: t('inviteCreatedAt'),
                    dataIndex: 'created_at',
                    key: 'created_at',
                    width: 160,
                    render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
                  },
                  {
                    title: t('inviteUsedAt'),
                    dataIndex: 'used_at',
                    key: 'used_at',
                    width: 160,
                    render: (v: string | null) =>
                      v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—',
                  },
                ]}
              />
            </PageCard>
          </Col>
        )}
      </Row>

      <Modal
        title={t('createTokenModal')}
        open={showCreateModal}
        onCancel={() => setShowCreateModal(false)}
        footer={
          newToken
            ? [
                <Button key="close" onClick={() => setShowCreateModal(false)}>
                  {t('close')}
                </Button>,
              ]
            : [
                <Button key="cancel" onClick={() => setShowCreateModal(false)}>
                  {t('revokeCancel')}
                </Button>,
                <Button key="create" type="primary" loading={creating} onClick={handleCreate}>
                  {t('create')}
                </Button>,
              ]
        }
      >
        {newToken ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text strong>{t('tokenCreatedHint')}</Typography.Text>
            <Input.TextArea
              value={newToken.token}
              readOnly
              rows={2}
              style={{ fontFamily: FONT_MONO }}
            />
            <Button icon={<CopyOutlined />} onClick={() => copyToken(newToken.token)}>
              {t('copyToken')}
            </Button>
          </Space>
        ) : (
          <div>
            <Typography.Paragraph type="secondary">{t('tokenNameHint')}</Typography.Paragraph>
            <Input
              prefix={<KeyOutlined />}
              placeholder={t('tokenNamePlaceholder')}
              value={tokenName}
              onChange={(e) => setTokenName(e.target.value)}
            />
          </div>
        )}
      </Modal>

      <Modal
        title={t('generateInviteModal')}
        open={showInviteModal}
        onCancel={() => setShowInviteModal(false)}
        width={520}
        footer={
          newInviteCodes
            ? [
                <Button key="close" onClick={() => setShowInviteModal(false)}>
                  {t('close')}
                </Button>,
              ]
            : [
                <Button key="cancel" onClick={() => setShowInviteModal(false)}>
                  {t('revokeCancel')}
                </Button>,
              ]
        }
      >
        {newInviteCodes ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text strong>
              {t('inviteCreatedHint', { count: newInviteCodes.count })}
            </Typography.Text>
            <Input.TextArea
              value={newInviteCodes.codes.join('\n')}
              readOnly
              rows={Math.min(newInviteCodes.codes.length, 8)}
              style={{ fontFamily: FONT_MONO }}
            />
            <Button
              icon={<CopyOutlined />}
              onClick={() => copyToken(newInviteCodes.codes.join('\n'))}
            >
              {t('copyCodes')}
            </Button>
          </Space>
        ) : (
          <Tabs
            defaultActiveKey="random"
            items={[
              {
                key: 'random',
                label: t('randomGenerate'),
                children: (
                  <div style={{ padding: '12px 0' }}>
                    <Typography.Paragraph type="secondary">{t('inviteCountHint')}</Typography.Paragraph>
                    <Space>
                      <InputNumber
                        min={1}
                        max={100}
                        value={inviteCount}
                        onChange={(v) => setInviteCount(v ?? 1)}
                      />
                      <Button
                        type="primary"
                        loading={creatingInvite}
                        onClick={() => handleCreateInviteCodes('random')}
                      >
                        {t('create')}
                      </Button>
                    </Space>
                  </div>
                ),
              },
              {
                key: 'manual',
                label: t('manualInput'),
                children: (
                  <div style={{ padding: '12px 0' }}>
                    <Typography.Paragraph type="secondary">{t('manualCodesHint')}</Typography.Paragraph>
                    <Input.TextArea
                      rows={4}
                      value={manualCodes}
                      onChange={(e) => setManualCodes(e.target.value)}
                      placeholder={t('manualCodesPlaceholder')}
                    />
                    <Button
                      type="primary"
                      loading={creatingInvite}
                      style={{ marginTop: 12 }}
                      onClick={() => handleCreateInviteCodes('manual')}
                    >
                      {t('create')}
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Modal>
    </PageShell>
  );
}
