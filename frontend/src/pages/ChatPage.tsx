import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Button, Drawer, Grid, Layout, message, Popconfirm, Space, Tag, Typography, theme } from 'antd';
import { CloseCircleOutlined, MenuOutlined, MessageOutlined } from '@ant-design/icons';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { ConversationList } from '@/components/chat/ConversationList';
import { MessageList } from '@/components/chat/MessageList';
import { Composer } from '@/components/chat/Composer';
import { CostBadge } from '@/components/chat/CostBadge';
import {
  useConversationQuery,
  useConversationsQuery,
  useCreateConversationMutation,
} from '@/hooks/chat/useChatQueries';
import { useChatStore } from '@/stores/chatStore';
import { useChatTurnStream } from '@/hooks/useChatTurnStream';
import { generatePrdFromMessages } from '@/api/chat';
import { useRunTaskStore } from '@/stores/runTaskStore';

export function ChatPage() {
  const { t } = useTranslation('chat');
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const isNarrow = !screens.md;
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const [createAgentLoading, setCreateAgentLoading] = useState(false);

  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const inFlight = useChatStore((s) => s.inFlight);
  const activeTraceId = useChatStore((s) => s.activeTraceId);
  const sessionTokenUsage = useChatStore((s) => s.sessionTokenUsage);
  const cacheTokensSaved = useChatStore((s) => s.cacheTokensSaved);
  const selectedMessageIds = useChatStore((s) => s.selectedMessageIds);
  const handleLiveEvent = useChatStore((s) => s.handleLiveEvent);

  const selectConversation = useChatStore((s) => s.selectConversation);
  const createAndSelectConversation = useChatStore((s) => s.createAndSelectConversation);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const cancelCurrentTurn = useChatStore((s) => s.cancelCurrentTurn);
  const onTurnTerminated = useChatStore((s) => s.onTurnTerminated);
  const removeConversation = useChatStore((s) => s.removeConversation);
  const renameConversation = useChatStore((s) => s.renameConversation);
  const toggleMessageSelection = useChatStore((s) => s.toggleMessageSelection);
  const clearSelection = useChatStore((s) => s.clearSelection);

  const { data: conversationsData, isLoading: conversationsLoading } = useConversationsQuery();
  const { data: conversationDetail, isLoading: activeLoading } =
    useConversationQuery(activeConversationId);

  const conversations = conversationsData?.items ?? [];
  const activeConversation = conversationDetail?.conversation ?? null;
  const activeMessages = conversationDetail?.messages ?? [];

  const createConversationMutation = useCreateConversationMutation();
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current || conversationsLoading) return;
    initialized.current = true;

    (async () => {
      if (conversations.length > 0) {
        selectConversation(conversations[0].conversation_id);
      } else {
        await createAndSelectConversation();
      }
    })();
  }, [
    conversationsLoading,
    conversations,
    selectConversation,
    createAndSelectConversation,
  ]);

  useChatTurnStream(activeTraceId, {
    enabled: Boolean(activeTraceId),
    onEvent: (e) => handleLiveEvent(e),
    onTerminated: () => {
      void onTurnTerminated();
    },
  });

  const conversationListProps = {
    conversations,
    loading: conversationsLoading,
    activeId: activeConversationId,
    onSelect: (id: string) => {
      selectConversation(id);
      setDrawerOpen(false);
    },
    onCreate: () =>
      void createConversationMutation.mutateAsync().then((c) => {
        selectConversation(c.conversation_id);
        setDrawerOpen(false);
      }),
    onDelete: (id: string) => void removeConversation(id),
  };

  const handleCreateAgentTask = async () => {
    const convId = activeConversationId;
    if (!convId || selectedMessageIds.size === 0) return;

    setCreateAgentLoading(true);
    try {
      const result = await generatePrdFromMessages(
        convId,
        Array.from(selectedMessageIds),
      );

      const runStore = useRunTaskStore.getState();
      runStore.setPrdContent(result.prd);
      runStore.setGoal(result.prd);

      clearSelection();
      navigate('/run-task');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to generate PRD';
      message.error(msg);
    } finally {
      setCreateAgentLoading(false);
    }
  };

  return (
    <PageShell className="page-shell--fill">
      <PageHero
        title={t('pageTitle')}
        subtitle={t('pageSubtitle')}
        icon={<MessageOutlined />}
        gradient="blue"
      />

      <Layout
        hasSider={!isNarrow}
        className="page-panel"
        style={{
          background: token.colorBgContainer,
          overflow: 'hidden',
        }}
      >
      {!isNarrow && <ConversationList {...conversationListProps} />}

      <Drawer
        title={t('conversationList')}
        placement="left"
        open={isNarrow && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={280}
        styles={{ body: { padding: 0 } }}
      >
        <ConversationList {...conversationListProps} embedded />
      </Drawer>

      <Layout
        className="chat-pane"
        data-theme="light"
      >
        <div
          style={{
            padding: '10px 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: 'rgba(255, 255, 255, 0.72)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <Space wrap>
            {isNarrow && (
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setDrawerOpen(true)}
                aria-label={t('conversationList')}
              />
            )}
            <Typography.Text
              strong
              editable={{
                text: activeConversation?.title || t('newConversation'),
                onChange(text) {
                  const id = activeConversationId;
                  if (id && text.trim()) {
                    void renameConversation(id, text.trim());
                  }
                },
                triggerType: ['text'],
              }}
            >
              {activeLoading && !activeConversation
                ? t('newConversation')
                : activeConversation?.title || t('newConversation')}
            </Typography.Text>
            {activeConversation?.conversation_id && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <code>{activeConversation.conversation_id}</code>
              </Typography.Text>
            )}
            {inFlight && <Tag color="processing">{t('running')}</Tag>}
            <CostBadge usage={sessionTokenUsage} cacheTokensSaved={cacheTokensSaved} />
          </Space>

          <Space>
            {selectedMessageIds.size > 0 && (
              <Button
                type="primary"
                loading={createAgentLoading}
                onClick={() => void handleCreateAgentTask()}
              >
                {t('createAgentTask', { count: selectedMessageIds.size })}
              </Button>
            )}

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
          </Space>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <MessageList
            messages={activeMessages}
            inFlight={inFlight}
            selectedMessageIds={selectedMessageIds}
            onToggleMessageSelection={toggleMessageSelection}
          />
          <div className="chat-composer-bar" style={{ padding: 12 }}>
            <Composer
              disabled={inFlight || !activeConversationId}
              onSend={(text) => void sendMessage(text)}
            />
          </div>
        </div>
      </Layout>
    </Layout>
    </PageShell>
  );
}
