import { useEffect, useMemo, useRef, useState } from 'react';
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
  const [bubbleColor, setBubbleColor] = useState<string>(() => {
    try { return localStorage.getItem('chat-bubble-color') || '#5c838c'; } catch { return '#5c838c'; }
  });

  /** 根据 hex 计算亮度 → 浅色底配深字，深色底配白字 */
  const bubbleLuminance = useMemo(() => {
    const hex = bubbleColor.replace('#', '');
    if (hex.length !== 6) return { isLight: false, text: '#FFFFFF', border: 'rgba(255,255,255,0.15)' };
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    // Relative luminance (sRGB)
    const lum = 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255);
    if (lum > 0.55) {
      return { isLight: true, text: '#1C2636', border: 'rgba(0,0,0,0.1)' };
    }
    return { isLight: false, text: '#FFFFFF', border: 'rgba(255,255,255,0.15)' };
  }, [bubbleColor]);

  const handleBubbleColorChange = (color: string) => {
    setBubbleColor(color);
    try { localStorage.setItem('chat-bubble-color', color); } catch { /* noop */ }
  };

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
        style={{
          '--chat-bubble-custom': bubbleColor,
          '--chat-user-text': bubbleLuminance.text,
          '--chat-user-border-custom': bubbleLuminance.border,
        } as React.CSSProperties}
      >
        <div
          style={{
            padding: '10px 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: 'rgba(255, 255, 255, 0.72)',
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
            <CostBadge usage={sessionTokenUsage} cacheTokensSaved={cacheTokensSaved} />
          </Space>

          <Space>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <input
                type="color"
                value={bubbleColor}
                onChange={(e) => handleBubbleColorChange(e.target.value)}
                title={t('bubbleColor') || '气泡配色'}
                style={{
                  width: 26,
                  height: 26,
                  padding: 0,
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: 'none',
                }}
              />
              <input
                type="text"
                value={bubbleColor}
                onChange={(e) => handleBubbleColorChange(e.target.value)}
                placeholder="#5c838c"
                style={{
                  width: 80,
                  height: 26,
                  padding: '2px 6px',
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: 6,
                  fontSize: 12,
                  fontFamily: 'monospace',
                  textAlign: 'center',
                  background: token.colorBgContainer,
                  color: token.colorText,
                }}
              />
            </div>
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
