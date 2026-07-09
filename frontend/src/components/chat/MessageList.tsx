import { useCallback, useRef, useState } from 'react';
import { Button, Empty, Typography } from 'antd';
import { VerticalAlignBottomOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import type { ChatMessage } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { MessageBubble } from './MessageBubble';
import { StreamingBubble } from './StreamingBubble';
import './ChatMessage.css';

interface Props {
  messages: ChatMessage[];
  inFlight: boolean;
  selectedMessageIds: Set<number>;
  onToggleMessageSelection: (messageId: number) => void;
}

function LiveFooter({ inFlight }: { inFlight: boolean }) {
  const { t } = useTranslation('chat');
  const streamingText = useChatStore((s) => s.liveStreamingText);

  if (!inFlight) return null;

  return (
    <div style={{ paddingBottom: 8 }}>
      <StreamingBubble />
      {!streamingText && (
        <div style={{ display: 'flex', alignItems: 'center', padding: '4px 16px' }}>
          <div className="thinking-indicator">
            <div className="thinking-dots">
              <span />
              <span />
              <span />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {t('agentThinking')}
            </Typography.Text>
          </div>
        </div>
      )}
    </div>
  );
}

/** 虚拟化消息列表 + 智能粘底滚动 */
export function MessageList({
  messages,
  inFlight,
  selectedMessageIds,
  onToggleMessageSelection,
}: Props) {
  const { t } = useTranslation('chat');
  const [atBottom, setAtBottom] = useState(true);
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  const Footer = useCallback(
    () => <LiveFooter inFlight={inFlight} />,
    [inFlight],
  );

  const isIdle = messages.length === 0 && !inFlight;

  if (isIdle) {
    return (
      <div
        className="chat-thread"
        data-theme="light"
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
      data-theme="light"
      style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex' }}
    >
      <Virtuoso
        ref={virtuosoRef}
        style={{ flex: 1 }}
        data={messages}
        atBottomStateChange={setAtBottom}
        followOutput={(isAtBottom) => (isAtBottom ? 'auto' : false)}
        itemContent={(_index, message) => (
          <MessageBubble
            message={message}
            selectable={true}
            selected={selectedMessageIds.has(message.id)}
            onToggleSelect={onToggleMessageSelection}
          />
        )}
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
