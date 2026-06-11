import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Layout, Popconfirm, Space, Tag, Typography, theme } from 'antd';
import { CloseCircleOutlined } from '@ant-design/icons';
import { ConversationList } from '@/components/chat/ConversationList';
import { MessageList } from '@/components/chat/MessageList';
import { Composer } from '@/components/chat/Composer';
import { useChatStore } from '@/stores/chatStore';
import { useChatTurnStream } from '@/hooks/useChatTurnStream';

export function ChatPage() {
  const { t } = useTranslation('chat');
  const { token } = theme.useToken();

  const conversations = useChatStore((s) => s.conversations);
  const conversationsLoading = useChatStore((s) => s.conversationsLoading);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const activeConversation = useChatStore((s) => s.activeConversation);
  const activeMessages = useChatStore((s) => s.activeMessages);
  const liveToolCalls = useChatStore((s) => s.liveToolCalls);
  const pendingPlan = useChatStore((s) => s.pendingPlan);
  const inFlight = useChatStore((s) => s.inFlight);
  const activeTraceId = useChatStore((s) => s.activeTraceId);
  const agenticMode = useChatStore((s) => s.agenticMode);
  const handleLiveEvent = useChatStore((s) => s.handleLiveEvent);

  const fetchConversations = useChatStore((s) => s.fetchConversations);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const startNewConversation = useChatStore((s) => s.startNewConversation);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const cancelCurrentTurn = useChatStore((s) => s.cancelCurrentTurn);
  const confirmPlan = useChatStore((s) => s.confirmPlan);
  const onTurnTerminated = useChatStore((s) => s.onTurnTerminated);
  const removeConversation = useChatStore((s) => s.removeConversation);

  const initialized = useRef(false);

  // 首次进入：拉会话列表 → 选首个，没有就新建
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    (async () => {
      await fetchConversations();
      const list = useChatStore.getState().conversations;
      if (list.length > 0) {
        await selectConversation(list[0].conversation_id);
      } else {
        await startNewConversation();
      }
    })();
  }, [fetchConversations, selectConversation, startNewConversation]);

  // 订阅当前轮 SSE — 实时事件注入 store，terminal 触发刷新
  useChatTurnStream(activeTraceId, {
    enabled: Boolean(activeTraceId),
    onEvent: (e) => handleLiveEvent(e),
    onTerminated: () => {
      void onTurnTerminated();
    },
  });

  return (
    <Layout
      hasSider
      style={{
        height: 'calc(100vh - 56px - 48px)' /* 减去 Header 和 Content 内边距 */,
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <ConversationList
        conversations={conversations}
        loading={conversationsLoading}
        activeId={activeConversationId}
        onSelect={(id) => void selectConversation(id)}
        onCreate={() => void startNewConversation()}
        onDelete={(id) => void removeConversation(id)}
      />

      <Layout style={{ background: token.colorBgLayout }}>
        <div
          style={{
            padding: '10px 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: token.colorBgContainer,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <Space>
            <Typography.Text
              strong
              editable={{
                text: activeConversation?.title || t('newConversation'),
                onChange(text) {
                  const id = activeConversationId;
                  if (id && text.trim()) {
                    useChatStore.getState().renameConversation(id, text.trim());
                  }
                },
                triggerType: ['text'],
              }}
            >
              {activeConversation?.title || t('newConversation')}
            </Typography.Text>
            {activeConversation?.conversation_id && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <code>{activeConversation.conversation_id}</code>
              </Typography.Text>
            )}
            {inFlight && <Tag color="processing">{t('running')}</Tag>}
            {agenticMode ? (
              <Tag color="orange">{t('agenticMode')}</Tag>
            ) : (
              inFlight && <Tag color="blue">{t('chatMode')}</Tag>
            )}
          </Space>

          {inFlight && activeTraceId && (
            <Popconfirm
              title={t('cancelTurn')}
              description={t('cancelTurnDesc')}
              onConfirm={() => void cancelCurrentTurn()}
              okText={t('cancelOk')}
              cancelText={t('cancelWait')}
            >
              <Button danger size="small" icon={<CloseCircleOutlined />}>
                {t('cancelOk')}
              </Button>
            </Popconfirm>
          )}
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <MessageList
            messages={activeMessages}
            liveToolCalls={liveToolCalls}
            pendingPlan={pendingPlan}
            inFlight={inFlight}
            agenticMode={agenticMode}
            onConfirmPlan={() => void confirmPlan('confirm')}
            onRejectPlan={() => void confirmPlan('reject')}
          />
          <div
            style={{
              padding: 12,
              borderTop: `1px solid ${token.colorBorderSecondary}`,
              background: token.colorBgContainer,
            }}
          >
            <Composer
              disabled={inFlight || !activeConversationId}
              onSend={(text) => void sendMessage(text)}
            />
          </div>
        </div>
      </Layout>
    </Layout>
  );
}
