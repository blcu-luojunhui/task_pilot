import { RobotOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import type { ChatMessage } from '@/api/types';
import { useSemanticColors } from '@/hooks/useSemanticColors';
import { buildMessageParts } from '@/utils/messageParts';
import { MessageRenderer } from './MessageRenderer';
import './ChatMessage.css';

interface Props {
  message: ChatMessage;
  streaming?: boolean;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (messageId: number) => void;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (isToday) return time;
    return `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`;
  } catch {
    return '';
  }
}

export function MessageBubble({ message, streaming = false, selectable = false, selected = false, onToggleSelect }: Props) {
  const palette = useSemanticColors();
  const { t } = useTranslation('chat');
  const parts = useMemo(() => buildMessageParts(message), [message]);

  if (message.role === 'system') return null;

  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const isTool = message.role === 'tool';

  const rowClass = [
    'msg-row',
    isUser ? 'user' : isAssistant ? 'assistant' : 'tool',
    selected ? 'msg-row--selected' : '',
  ].join(' ');

  const handleClick = () => {
    if (selectable && onToggleSelect && message.id > 0) {
      onToggleSelect(message.id);
    }
  };

  const textParts = parts.filter((p) => p.kind === 'text');
  const inlineParts = parts.filter((p) => p.kind !== 'text');
  const hasBubbleContent = textParts.length > 0 || (streaming && isAssistant);

  const bubbleClass = [
    'msg-bubble',
    isUser ? 'msg-bubble--user' : isAssistant ? 'msg-bubble--assistant' : 'msg-bubble--tool',
  ].join(' ');

  const toolAvatarStyle: React.CSSProperties = {
    background: palette.toolAvatarBg,
    color: palette.toolAvatarText,
    border: `1px solid ${palette.toolAvatarBorder}`,
  };

  const toolBubbleStyle: React.CSSProperties = {
    background: palette.toolAvatarBg,
    border: `1px solid ${palette.toolAvatarBorder}`,
    boxShadow: 'var(--chat-assistant-shadow)',
  };

  return (
    <div className={rowClass} onClick={handleClick} style={{ cursor: selectable ? 'pointer' : undefined }}>
      {selectable && (
        <div
          className={`msg-select-checkbox${selected ? ' msg-select-checkbox--checked' : ''}`}
          onClick={(e) => {
            e.stopPropagation();
            if (onToggleSelect && message.id > 0) onToggleSelect(message.id);
          }}
        >
          {selected && '✓'}
        </div>
      )}
      {!isUser && (
        <div className="msg-avatar" style={isTool ? toolAvatarStyle : undefined}>
          {isAssistant ? <RobotOutlined /> : <ToolOutlined />}
        </div>
      )}

      <div className="msg-body">
        <div className="msg-meta">
          <span className="msg-meta__name">
            {isUser ? t('you') : isAssistant ? t('agent') : `${t('toolPrefix')} ${message.tool_call_id ?? ''}`}
          </span>
          {message.created_at && (
            <span className="msg-meta__time">{formatTime(message.created_at)}</span>
          )}
          {message.trace_id && !isUser && (
            <Link
              to={`/tasks/${encodeURIComponent(message.trace_id)}`}
              className="msg-meta__trace"
            >
              trace
            </Link>
          )}
        </div>

        {hasBubbleContent && (
          <div className={bubbleClass} style={isTool ? toolBubbleStyle : undefined}>
            <MessageRenderer
              parts={textParts.length > 0 ? textParts : [{ kind: 'text', text: '' }]}
              isUser={isUser}
              streaming={streaming}
            />
          </div>
        )}

        {inlineParts.length > 0 && (
          <div
            className={`msg-inline-parts${hasBubbleContent ? '' : ' msg-inline-parts--only'}`}
          >
            <MessageRenderer parts={inlineParts} isUser={isUser} />
          </div>
        )}
      </div>

      {isUser && (
        <div className="msg-avatar">
          <UserOutlined />
        </div>
      )}
    </div>
  );
}
