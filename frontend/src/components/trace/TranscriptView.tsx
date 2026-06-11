import { useState } from 'react';
import { Typography, Tag, Space, Collapse, Empty } from 'antd';
import {
  RobotOutlined,
  ToolOutlined,
  UserOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TraceEvent } from '@/api/types';

interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: Array<{ id?: string; name?: string; arguments?: unknown }>;
  tool_call_id?: string;
  step: number | null;
}

function extractMessages(events: TraceEvent[]): Message[] {
  const messages: Message[] = [];

  for (const evt of events) {
    const data = evt.data as Record<string, unknown>;

    if (evt.type === 'run_start') {
      const meta = data.metadata as Record<string, unknown> | undefined;
      if (meta?.goal) {
        messages.push({
          role: 'user',
          content: String(meta.goal),
          step: null,
        });
      }
    }

    if (evt.type === 'think_end') {
      const msg = data.assistant_message as
        | { role?: string; content?: string; tool_calls?: Array<{ id?: string; function?: { name: string; arguments: string }; name?: string; arguments?: unknown }> }
        | undefined;
      if (!msg) continue;

      const toolCalls = msg.tool_calls?.map((tc) => {
        const func = tc.function || tc;
        let args = func.arguments ?? tc.arguments;
        if (typeof args === 'string') {
          try { args = JSON.parse(args); } catch { /* keep as string */ }
        }
        return { id: tc.id, name: func.name || tc.name, arguments: args };
      });

      messages.push({
        role: 'assistant',
        content: msg.content?.trim() || '',
        tool_calls: toolCalls,
        step: evt.step,
      });
    }

    if (evt.type === 'act_end') {
      const results = data.tool_results as Array<{ tool_call_id?: string; content?: string }> | undefined;
      if (!results) continue;
      for (const r of results) {
        messages.push({
          role: 'tool',
          content: String(r.content ?? ''),
          tool_call_id: r.tool_call_id ?? '',
          step: evt.step,
        });
      }
    }

    if (evt.type === 'feedback_collected') {
      const fb = data.messages as Array<{ role: string; content: string }> | undefined;
      if (fb) {
        for (const m of fb) {
          messages.push({
            role: m.role as Message['role'],
            content: m.content,
            step: evt.step,
          });
        }
      }
    }
  }

  return messages;
}

function getRoleConfig(t: (key: string) => string): Record<string, { icon: React.ReactNode; bg: string; label: string; defaultCollapse: boolean }> {
  return {
    system: { icon: <SettingOutlined />, bg: '#f5f5f5', label: t('transcript.system'), defaultCollapse: true },
    user: { icon: <UserOutlined />, bg: '#e6f4ff', label: t('transcript.user'), defaultCollapse: false },
    assistant: { icon: <RobotOutlined />, bg: '#fffbe6', label: t('transcript.assistant'), defaultCollapse: false },
    tool: { icon: <ToolOutlined />, bg: '#f6ffed', label: t('transcript.tool'), defaultCollapse: false },
  };
}

export function TranscriptView({ events }: { events: TraceEvent[] }) {
  const messages = extractMessages(events);
  const { t } = useTranslation('trace');

  if (messages.length === 0) {
    return <Empty description={t('transcript.noData')} />;
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%', padding: '8px 0' }}>
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} index={i} t={t} />
      ))}
    </Space>
  );
}

function MessageBubble({ message, index, t }: { message: Message; index: number; t: (key: string, opts?: Record<string, unknown>) => string }) {
  const [expanded, setExpanded] = useState(false);
  const config = getRoleConfig(t)[message.role] ?? getRoleConfig(t).assistant;
  const shouldCollapse = config.defaultCollapse || message.content.length > 500;
  const displayContent = expanded || !shouldCollapse
    ? message.content
    : (message.content.slice(0, 500) + '...');

  return (
    <div
      style={{
        background: config.bg,
        borderRadius: 8,
        padding: '8px 12px',
        border: '1px solid #f0f0f0',
      }}
    >
      <Space size={4} style={{ marginBottom: 4 }}>
        {config.icon}
        <Tag color="default" style={{ margin: 0 }}>{config.label}</Tag>
        {message.step !== null && (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            step {message.step}
          </Typography.Text>
        )}
        {message.tool_call_id && (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            id={message.tool_call_id.slice(0, 12)}...
          </Typography.Text>
        )}
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          #{index + 1}
        </Typography.Text>
      </Space>

      {message.tool_calls && message.tool_calls.length > 0 && (
        <Collapse
          size="small"
          ghost
          items={[
            {
              key: 'calls',
              label: (
                <Typography.Text style={{ fontSize: 12 }}>
                  {t('transcript.toolCallsCount', { count: message.tool_calls.length })}
                </Typography.Text>
              ),
              children: (
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  {message.tool_calls.map((tc, i) => (
                    <Typography.Text key={i} style={{ fontSize: 11 }}>
                      <Tag color="geekblue">{tc.name}</Tag>
                      <code>{JSON.stringify(tc.arguments)}</code>
                    </Typography.Text>
                  ))}
                </Space>
              ),
            },
          ]}
        />
      )}

      {message.content && (
        <div>
          <Typography.Paragraph
            style={{
              margin: 0,
              marginTop: 4,
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: message.role === 'system'
                ? 'ui-monospace, SFMono-Regular, monospace'
                : undefined,
            }}
          >
            {displayContent}
          </Typography.Paragraph>
          {shouldCollapse && (
            <Typography.Link
              style={{ fontSize: 11 }}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? t('transcript.collapse') : t('transcript.expand', { length: message.content.length })}
            </Typography.Link>
          )}
        </div>
      )}
    </div>
  );
}
