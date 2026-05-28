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
} from 'antd';
import { PlusOutlined, KeyOutlined, CopyOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/authStore';
import {
  type TokenInfo,
  type CreateTokenResult,
  createToken,
  listTokens,
  revokeToken,
} from '@/api/auth';
import dayjs from 'dayjs';

export function AccountPage() {
  const account = useAuthStore((s) => s.account);
  const fetchMe = useAuthStore((s) => s.fetchMe);

  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [loadingTokens, setLoadingTokens] = useState(false);
  const [newToken, setNewToken] = useState<CreateTokenResult | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [tokenName, setTokenName] = useState('');
  const [creating, setCreating] = useState(false);

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
      message.success('令牌已吊销');
      await loadTokens();
    } catch {
      // handled by interceptor
    }
  };

  const copyToken = (text: string) => {
    navigator.clipboard.writeText(text).then(
      () => message.success('已复制到剪贴板'),
      () => message.warning('复制失败，请手动复制'),
    );
  };

  if (!account) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const usagePercent = account.daily_token_limit > 0
    ? Math.round((account.today_tokens_used / account.daily_token_limit) * 100)
    : 0;

  const tokenColumns = [
    {
      title: '前缀',
      dataIndex: 'token_prefix',
      key: 'token_prefix',
      render: (v: string) => <code>{v}...</code>,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string | null) => v || <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm') : <Typography.Text type="secondary">从未使用</Typography.Text>,
    },
    {
      title: '过期时间',
      dataIndex: 'expires_at',
      key: 'expires_at',
      render: (v: string | null) =>
        v ? dayjs(v).format('YYYY-MM-DD HH:mm') : <Tag color="green">永不过期</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: TokenInfo) => (
        <Popconfirm
          title="吊销后该 token 将立即失效，确定？"
          onConfirm={() => handleRevoke(record.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button size="small" danger type="link">
            吊销
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 960 }}>
      <Typography.Title level={4}>账号管理</Typography.Title>

      {/* 基本信息 */}
      <Card size="small" style={{ marginBottom: 24 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="用户名">{account.username}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{account.email}</Descriptions.Item>
          <Descriptions.Item label="注册时间">
            {dayjs(account.created_at).format('YYYY-MM-DD HH:mm')}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 用量 */}
      <Row gutter={24} style={{ marginBottom: 24 }}>
        <Col span={12}>
          <Card size="small" title="今日 Token 用量">
            <Progress
              percent={usagePercent}
              status={usagePercent >= 100 ? 'exception' : 'active'}
              format={() => `${account.today_tokens_used.toLocaleString()} / ${account.daily_token_limit.toLocaleString()}`}
            />
          </Card>
        </Col>
      </Row>

      {/* Token 管理 */}
      <Card
        size="small"
        title="访问令牌"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            size="small"
            onClick={() => {
              setNewToken(null);
              setTokenName('');
              setShowCreateModal(true);
            }}
          >
            创建令牌
          </Button>
        }
      >
        <Table
          dataSource={tokens}
          columns={tokenColumns}
          rowKey="id"
          loading={loadingTokens}
          pagination={false}
          size="small"
        />
      </Card>

      {/* 创建 Token 弹窗 */}
      <Modal
        title="创建访问令牌"
        open={showCreateModal}
        onCancel={() => setShowCreateModal(false)}
        footer={newToken ? [
          <Button key="close" onClick={() => setShowCreateModal(false)}>
            关闭
          </Button>,
        ] : [
          <Button key="cancel" onClick={() => setShowCreateModal(false)}>
            取消
          </Button>,
          <Button key="create" type="primary" loading={creating} onClick={handleCreate}>
            创建
          </Button>,
        ]}
      >
        {newToken ? (
          <div>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text strong>
                令牌已创建，请立即复制保存，关闭后无法再次查看：
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
                复制令牌
              </Button>
            </Space>
          </div>
        ) : (
          <div>
            <Typography.Paragraph type="secondary">
              为新令牌添加备注名称（可选）
            </Typography.Paragraph>
            <Input
              prefix={<KeyOutlined />}
              placeholder="令牌名称（可选）"
              value={tokenName}
              onChange={(e) => setTokenName(e.target.value)}
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
