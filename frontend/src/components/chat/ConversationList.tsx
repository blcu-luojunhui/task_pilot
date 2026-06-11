import { Button, Empty, Popconfirm, Space, Spin, Tooltip, Typography, theme } from 'antd';
import { DeleteOutlined, MessageOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { ChatConversation } from '@/api/types';

interface Props {
  conversations: ChatConversation[];
  loading?: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  /** 抽屉内全宽展示（窄屏 FE-9） */
  embedded?: boolean;
}

export function ConversationList({
  conversations,
  loading,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  embedded = false,
}: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');

  return (
    <div
      style={{
        width: embedded ? '100%' : 240,
        borderRight: embedded ? undefined : `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: token.colorBgContainer,
      }}
    >
      <div style={{ padding: 12, borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
        <Button block type="primary" icon={<PlusOutlined />} onClick={onCreate}>
          {t('newConversation')}
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
              description={<Typography.Text type="secondary">{t('noConversations')}</Typography.Text>}
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
                      {c.title || t('unnamedConversation')}
                    </Typography.Text>
                  </Space>
                  <Popconfirm
                    title={t('deleteConversation')}
                    description={t('deleteDesc')}
                    onConfirm={() => onDelete(c.conversation_id)}
                    okText={t('deleteOk')}
                    cancelText={t('deleteCancel')}
                  >
                    <Tooltip title={t('deleteOk')}>
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
