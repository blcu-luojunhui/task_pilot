import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Drawer, Grid, Layout, Popconfirm, Space, Tag, Typography, theme } from 'antd';
import { CloseCircleOutlined, MenuOutlined, MessageOutlined } from '@ant-design/icons';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { ConversationList } from '@/components/chat/ConversationList';
import { MessageList } from '@/components/chat/MessageList';
import { Composer } from '@/components/chat/Composer';
import { AgentControlBar } from '@/components/chat/AgentControlBar';
import { CostBadge } from '@/components/chat/CostBadge';
import { StrategyBadge } from '@/components/chat/StrategyBadge';
import {
  useConversationQuery,
  useConversationsQuery,
  useCreateConversationMutation,
} from '@/hooks/chat/useChatQueries';
import { useChatStore } from '@/stores/chatStore';
import { useChatTurnStream } from '@/hooks/useChatTurnStream';
import { useDarkMode } from '@/hooks/useDarkMode';

export function ChatPage() {
  const { t } = useTranslation('chat');
  const { token } = theme.useToken();
  const [dark] = useDarkMode();
  const screens = Grid.useBreakpoint();
  const isNarrow = !screens.md;
  const [drawerOpen, setDrawerOpen] = useState(false);

  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const liveToolCalls = useChatStore((s) => s.liveToolCalls);
  const pendingPlan = useChatStore((s) => s.pendingPlan);
  const inFlight = useChatStore((s) => s.inFlight);
  const activeTraceId = useChatStore((s) => s.activeTraceId);
  const agenticMode = useChatStore((s) => s.agenticMode);
  const plan = useChatStore((s) => s.plan);
  const strategy = useChatStore((s) => s.strategy);
  const liveReasoning = useChatStore((s) => s.liveReasoning);
  const reflections = useChatStore((s) => s.reflections);
  const sessionTokenUsage = useChatStore((s) => s.sessionTokenUsage);
  const cacheTokensSaved = useChatStore((s) => s.cacheTokensSaved);
  const artifacts = useChatStore((s) => s.artifacts);
  const compactionNotices = useChatStore((s) => s.compactionNotices);
  const lifecycle = useChatStore((s) => s.lifecycle);
  const controlLoading = useChatStore((s) => s.controlLoading);
  const handleLiveEvent = useChatStore((s) => s.handleLiveEvent);

  const selectConversation = useChatStore((s) => s.selectConversation);
  const createAndSelectConversation = useChatStore((s) => s.createAndSelectConversation);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const cancelCurrentTurn = useChatStore((s) => s.cancelCurrentTurn);
  const confirmPlan = useChatStore((s) => s.confirmPlan);
  const onTurnTerminated = useChatStore((s) => s.onTurnTerminated);
  const removeConversation = useChatStore((s) => s.removeConversation);
  const pauseCurrentAgent = useChatStore((s) => s.pauseCurrentAgent);
  const resumeCurrentAgent = useChatStore((s) => s.resumeCurrentAgent);
  const stopCurrentAgent = useChatStore((s) => s.stopCurrentAgent);
  const saveCurrentSnapshot = useChatStore((s) => s.saveCurrentSnapshot);
  const renameConversation = useChatStore((s) => s.renameConversation);

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

      <Layout className="chat-pane" data-theme={dark ? 'dark' : 'light'}>
        <div
          style={{
            padding: '10px 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: dark ? 'rgba(28, 28, 30, 0.65)' : 'rgba(255, 255, 255, 0.72)',
            backdropFilter: 'blur(12px)',
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
            <StrategyBadge strategy={strategy} />
            <CostBadge usage={sessionTokenUsage} cacheTokensSaved={cacheTokensSaved} />
            {agenticMode ? (
              <Tag color="orange">{t('agenticMode')}</Tag>
            ) : (
              inFlight && <Tag color="blue">{t('chatMode')}</Tag>
            )}
          </Space>

          <AgentControlBar
            lifecycle={lifecycle}
            traceId={activeTraceId}
            loading={controlLoading}
            onPause={() => void pauseCurrentAgent()}
            onResume={() => void resumeCurrentAgent()}
            onStop={() => void stopCurrentAgent()}
            onSaveSnapshot={() => void saveCurrentSnapshot()}
          />

          {inFlight && activeTraceId && lifecycle === 'running' && (
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
            plan={plan}
            liveReasoning={liveReasoning}
            reflections={reflections}
            artifacts={artifacts}
            compactionNotices={compactionNotices}
            onConfirmPlan={() => void confirmPlan('confirm')}
            onRejectPlan={() => void confirmPlan('reject')}
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
