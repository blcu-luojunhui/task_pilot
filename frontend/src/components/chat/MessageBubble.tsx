import { useCallback, useState } from 'react';
import { Card, Space, Tag, Typography, theme } from 'antd';
import { RobotOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import type { ChatMessage, ChatToolCall } from '@/api/types';
import { PlanCard } from './PlanCard';
import './ChatMessage.css';

interface Props {
  message: ChatMessage;
  streaming?: boolean;
}

function extractToolCallSummary(tc: ChatToolCall): { name: string; args: string } {
  const name = tc.function?.name || tc.name || 'unknown';
  const rawArgs = tc.function?.arguments ?? tc.arguments ?? {};
  let argsStr = '';
  try {
    argsStr = typeof rawArgs === 'string' ? rawArgs : JSON.stringify(rawArgs, null, 2);
  } catch {
    argsStr = String(rawArgs);
  }
  return { name, args: argsStr };
}

function getTcName(tc: ChatToolCall): string {
  return tc.function?.name ?? tc.name ?? 'unknown';
}

function CodeBlock({ className, children }: { className?: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const lang = className?.replace('language-', '') || '';
  const codeStr = String(children).replace(/\n$/, '');
  const { t } = useTranslation('chat');

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(codeStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [codeStr]);

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{lang || 'code'}</span>
        <button className={`code-block-copy ${copied ? 'copied' : ''}`} onClick={handleCopy}>
          {copied ? t('copied') : t('copyCode')}
        </button>
      </div>
      <pre>
        <code className={className}>{codeStr}</code>
      </pre>
    </div>
  );
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

export function MessageBubble({ message, streaming = false }: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');

  if (message.role === 'system') return null;

  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const isTool = message.role === 'tool';

  const avatarStyle: React.CSSProperties = isUser
    ? { background: token.colorPrimary, color: '#fff' }
    : isAssistant
    ? { background: '#f6ffed', color: '#52c41a', border: '1px solid #b7eb8f' }
    : { background: '#fffbe6', color: '#faad14', border: '1px solid #ffe58f' };

  const bubbleBg = isUser
    ? token.colorPrimary
    : isTool
    ? token.colorWarningBg
    : token.colorBgContainer;

  const bubbleBorder = isUser
    ? token.colorPrimary
    : isTool
    ? token.colorWarningBorder
    : token.colorBorderSecondary;

  const bubbleTextColor = isUser ? '#fff' : undefined;

  const rowClass = `msg-row ${isUser ? 'user' : isAssistant ? 'assistant' : 'tool'}`;

  return (
    <div className={rowClass}>
      {!isUser && (
        <div className="msg-avatar" style={avatarStyle}>
          {isAssistant ? <RobotOutlined /> : <ToolOutlined />}
        </div>
      )}

      <div className="msg-body">
        {/* 元信息：名称 + 时间 + trace 链接 */}
        <div className="msg-meta">
          <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 500 }}>
            {isUser ? t('you') : isAssistant ? t('agent') : `${t('toolPrefix')} ${message.tool_call_id ?? ''}`}
          </Typography.Text>
          {message.created_at && (
            <Typography.Text type="secondary" style={{ fontSize: 11, opacity: 0.6 }}>
              {formatTime(message.created_at)}
            </Typography.Text>
          )}
          {message.trace_id && !isUser && (
            <Link
              to={`/tasks/${encodeURIComponent(message.trace_id)}`}
              style={{ fontSize: 11 }}
            >
              trace
            </Link>
          )}
        </div>

        {/* 消息气泡 */}
        {message.content && (
          <div
            className="msg-bubble markdown-body"
            style={{
              background: bubbleBg,
              border: `1px solid ${bubbleBorder}`,
              color: bubbleTextColor,
            }}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ className, children, ...props }) {
                  const isInline = !className;
                  if (isInline) {
                    return (
                      <code
                        style={{
                          background: isUser ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.06)',
                          color: isUser ? '#fff' : undefined,
                          padding: '1px 5px',
                          borderRadius: 4,
                          fontSize: '0.88em',
                        }}
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  }
                  return <CodeBlock className={className}>{children}</CodeBlock>;
                },
                a({ href, children, ...props }) {
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: isUser ? '#fff' : token.colorPrimary }}
                      {...props}
                    >
                      {children}
                    </a>
                  );
                },
                th({ children, ...props }) {
                  return (
                    <th
                      style={{
                        border: `1px solid ${isUser ? 'rgba(255,255,255,0.25)' : token.colorBorderSecondary}`,
                        padding: '7px 12px',
                        background: isUser ? 'rgba(255,255,255,0.1)' : token.colorFillTertiary,
                        fontWeight: 600,
                        textAlign: 'left',
                      }}
                      {...props}
                    >
                      {children}
                    </th>
                  );
                },
                td({ children, ...props }) {
                  return (
                    <td
                      style={{
                        border: `1px solid ${isUser ? 'rgba(255,255,255,0.25)' : token.colorBorderSecondary}`,
                        padding: '7px 12px',
                      }}
                      {...props}
                    >
                      {children}
                    </td>
                  );
                },
                hr() {
                  return <hr style={{ border: 'none', borderTop: `1px solid ${isUser ? 'rgba(255,255,255,0.25)' : token.colorBorderSecondary}` }} />;
                },
                blockquote({ children, ...props }) {
                  return (
                    <blockquote
                      style={{
                        borderLeft: `3px solid ${isUser ? 'rgba(255,255,255,0.4)' : token.colorPrimaryBorder}`,
                        color: isUser ? 'rgba(255,255,255,0.85)' : token.colorTextSecondary,
                      }}
                      {...props}
                    >
                      {children}
                    </blockquote>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
            {streaming && <span className="typing-cursor" />}
          </div>
        )}

        {/* 工具调用卡片（仅 assistant 消息） */}
        {isAssistant &&
          message.tool_calls &&
          message.tool_calls.length > 0 && (
            <Space direction="vertical" size={8} style={{ marginTop: 8, width: '100%' }}>
              {message.tool_calls.map((tc, i) => {
                const tcName = getTcName(tc);
                if (tcName === 'plan_tasks') {
                  return <PlanCard key={tc.id ?? i} toolCall={tc} />;
                }
                const { name, args } = extractToolCallSummary(tc);
                return (
                  <Card
                    key={tc.id ?? i}
                    size="small"
                    style={{ background: token.colorBgLayout }}
                    title={
                      <Space size={6}>
                        <ToolOutlined />
                        <Typography.Text strong>{name}</Typography.Text>
                        <Tag color="orange">{t('toolCallTag')}</Tag>
                      </Space>
                    }
                  >
                    <pre style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                      {args}
                    </pre>
                  </Card>
                );
              })}
            </Space>
          )}

        </div>

        {/* 用户消息的头像放右边 */}
        {isUser && (
          <div className="msg-avatar" style={avatarStyle}>
            <UserOutlined />
          </div>
        )}
      </div>
    );
  }
