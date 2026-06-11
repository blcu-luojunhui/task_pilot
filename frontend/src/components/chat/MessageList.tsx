import { useCallback, useRef, useState } from 'react';
import { Button, Empty, Typography, theme } from 'antd';
import { VerticalAlignBottomOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useDarkMode } from '@/hooks/useDarkMode';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import type { ArtifactRef, ChatMessage, PlanStep } from '@/api/types';
import type { PendingPlan, ToolCallStatus } from '@/stores/chatStore';
import { ArtifactCard } from './ArtifactCard';
import { CompactionNotice } from './CompactionNotice';
import { MessageBubble } from './MessageBubble';
import { PendingPlanCard } from './PendingPlanCard';
import { PlanPanel } from './PlanPanel';
import { ReasoningBlock } from './ReasoningBlock';
import { StreamingBubble } from './StreamingBubble';
import { ToolCallBlock } from './ToolCallBlock';
import './ChatMessage.css';

interface Props {
  messages: ChatMessage[];
  liveToolCalls: ToolCallStatus[];
  pendingPlan: PendingPlan | null;
  inFlight: boolean;
  agenticMode?: boolean;
  plan?: PlanStep[];
  liveReasoning?: string;
  reflections?: string[];
  artifacts?: ArtifactRef[];
  compactionNotices?: string[];
  confirmLoading?: boolean;
  onConfirmPlan?: () => void;
  onRejectPlan?: () => void;
}

function LiveFooter({
  liveToolCalls,
  pendingPlan,
  inFlight,
  agenticMode,
  plan,
  liveReasoning,
  reflections,
  artifacts,
  compactionNotices,
  confirmLoading,
  onConfirmPlan,
  onRejectPlan,
}: Omit<Props, 'messages'>) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');

  return (
    <div style={{ paddingBottom: 8 }}>
      {plan && plan.length > 0 && <PlanPanel steps={plan} compact />}

      {liveReasoning && (
        <div style={{ padding: '0 16px' }}>
          <ReasoningBlock text={liveReasoning} streaming={inFlight} />
        </div>
      )}

      {reflections?.map((text, i) => (
        <div key={`reflection-${i}`} style={{ padding: '0 16px' }}>
          <ReasoningBlock text={text} variant="reflection" />
        </div>
      ))}

      {compactionNotices?.map((msg, i) => (
        <CompactionNotice key={`compact-${i}`} message={msg} />
      ))}

      {artifacts?.map((a) => (
        <div key={a.id} style={{ padding: '4px 16px' }}>
          <ArtifactCard artifact={a} />
        </div>
      ))}

      <StreamingBubble />

      {liveToolCalls.map((tc, i) => (
        <ToolCallBlock key={tc.callId || `tc-${i}`} toolCall={tc} />
      ))}

      {pendingPlan && onConfirmPlan && onRejectPlan && (
        <PendingPlanCard
          toolCalls={pendingPlan.toolCalls}
          loading={confirmLoading ?? false}
          onConfirm={onConfirmPlan}
          onReject={onRejectPlan}
        />
      )}

      {inFlight && liveToolCalls.length === 0 && !pendingPlan && (
        <div style={{ display: 'flex', alignItems: 'center', padding: '4px 16px' }}>
          <div
            className="thinking-indicator"
            style={{
              background: token.colorSuccessBg,
              border: `1px solid ${token.colorSuccessBorder}`,
            }}
          >
            <div className="thinking-dots">
              <span />
              <span />
              <span />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {agenticMode ? t('agentExecuting') : t('agentThinking')}
            </Typography.Text>
          </div>
        </div>
      )}
    </div>
  );
}

/** 虚拟化消息列表 + 智能粘底滚动（FE-5） */
export function MessageList({
  messages,
  liveToolCalls,
  pendingPlan,
  inFlight,
  agenticMode = false,
  plan = [],
  liveReasoning = '',
  reflections = [],
  artifacts = [],
  compactionNotices = [],
  confirmLoading = false,
  onConfirmPlan,
  onRejectPlan,
}: Props) {
  const { t } = useTranslation('chat');
  const [dark] = useDarkMode();
  const [atBottom, setAtBottom] = useState(true);
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  const Footer = useCallback(
    () => (
      <LiveFooter
        liveToolCalls={liveToolCalls}
        pendingPlan={pendingPlan}
        inFlight={inFlight}
        agenticMode={agenticMode}
        plan={plan}
        liveReasoning={liveReasoning}
        reflections={reflections}
        artifacts={artifacts}
        compactionNotices={compactionNotices}
        confirmLoading={confirmLoading}
        onConfirmPlan={onConfirmPlan}
        onRejectPlan={onRejectPlan}
      />
    ),
    [
      liveToolCalls,
      pendingPlan,
      inFlight,
      agenticMode,
      plan,
      liveReasoning,
      reflections,
      artifacts,
      compactionNotices,
      confirmLoading,
      onConfirmPlan,
      onRejectPlan,
    ],
  );

  const isIdle =
    messages.length === 0 &&
    liveToolCalls.length === 0 &&
    !pendingPlan &&
    !inFlight &&
    plan.length === 0 &&
    !liveReasoning &&
    reflections.length === 0;

  if (isIdle) {
    return (
      <div
        className="chat-thread"
        data-theme={dark ? 'dark' : 'light'}
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Empty
          description={
            <Typography.Text type="secondary">{t('emptyHint')}</Typography.Text>
          }
        />
      </div>
    );
  }

  return (
    <div
      className="chat-thread"
      data-theme={dark ? 'dark' : 'light'}
      style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex' }}
    >
      <Virtuoso
        ref={virtuosoRef}
        style={{ flex: 1 }}
        data={messages}
        atBottomStateChange={setAtBottom}
        followOutput={(isAtBottom) => (isAtBottom ? 'auto' : false)}
        itemContent={(_index, message) => <MessageBubble message={message} />}
        components={{ Footer }}
      />
      {!atBottom && (
        <Button
          type="default"
          size="small"
          icon={<VerticalAlignBottomOutlined />}
          onClick={() => {
            virtuosoRef.current?.scrollToIndex({
              index: Math.max(0, messages.length - 1),
              behavior: 'smooth',
              align: 'end',
            });
          }}
          className="chat-scroll-bottom"
          style={{
            position: 'absolute',
            bottom: 16,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
          }}
        >
          {t('scrollToBottom')}
        </Button>
      )}
    </div>
  );
}
