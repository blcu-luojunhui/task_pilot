import { Button, Empty, Popconfirm, Space, Spin, Tooltip, Typography, theme } from 'antd';
import { DeleteOutlined, MessageOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ChatConversation } from '@/api/types';

interface Props {
  conversations: ChatConversation[];
  loading?: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

export function ConversationList({
  conversations,
  loading,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: Props) {
  const { token } = theme.useToken();

  return (
    <div
      style={{
        width: 240,
        borderRight: `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: token.colorBgContainer,
      }}
    >
      <div style={{ padding: 12, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <Button block type="primary" icon={<PlusOutlined />} onClick={onCreate}>
          新建会话
        </Button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading && conversations.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center' }}>
            <Spin />
          </div>
        ) : conversations.length === 0 ? (
          <div style={{ padding: 24 }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<Typography.Text type="secondary">还没有会话</Typography.Text>}
            />
          </div>
        ) : (
          conversations.map((c) => {
            const active = c.conversation_id === activeId;
            return (
              <div
                key={c.conversation_id}
                onClick={() => onSelect(c.conversation_id)}
                style={{
                  padding: '10px 12px',
                  cursor: 'pointer',
                  background: active ? token.colorPrimaryBg : 'transparent',
                  borderLeft: active
                    ? `3px solid ${token.colorPrimary}`
                    : '3px solid transparent',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
              >
                <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space size={6} style={{ minWidth: 0, flex: 1 }}>
                    <MessageOutlined style={{ color: token.colorPrimary }} />
                    <Typography.Text
                      strong={active}
                      ellipsis
                      style={{ fontSize: 13, maxWidth: 160 }}
                    >
                      {c.title || '未命名会话'}
                    </Typography.Text>
                  </Space>
                  <Popconfirm
                    title="删除会话"
                    description="删除后将不可见"
                    onConfirm={() => onDelete(c.conversation_id)}
                    okText="删除"
                    cancelText="取消"
                  >
                    <Tooltip title="删除">
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Tooltip>
                  </Popconfirm>
                </Space>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {dayjs(c.updated_at).format('MM-DD HH:mm')}
                </Typography.Text>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
