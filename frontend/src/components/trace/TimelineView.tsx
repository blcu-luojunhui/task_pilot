import { useState, type ReactNode } from 'react';
import { Button, Timeline, Tag, Typography, Space, Alert, theme } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import i18n from '@/locales/i18n';
import type { TraceEvent } from '@/api/types';
import { formatIso } from '@/utils/format';
import { SOURCE_COLOR } from '@/utils/colors';
import { FONT_MONO } from '@/utils/fonts';
import { ToolCallReplayModal } from './ToolCallReplayModal';

export function TimelineView({ events }: { events: TraceEvent[] }) {
  const [replayEvent, setReplayEvent] = useState<TraceEvent | null>(null);
  const { t } = useTranslation('trace');

  if (events.length === 0) {
    return <Alert type="warning" showIcon message={t('timeline.noEvents')} />;
  }

  const hasFailedActEnd = events.some((evt) => {
    if (evt.type !== 'act_end') return false;
    const data = evt.data as { tool_results?: Array<{ content?: string }> };
    return data.tool_results?.some((r) => (r.content ?? '').startsWith('Error:'));
  });

  return (
    <>
      <Timeline
        mode="left"
        items={events.map((evt) => ({
          label: (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatIso(evt.timestamp)}
              {evt.step !== null && (
                <>
                  <br />
                  <Tag style={{ marginTop: 2 }}>step {evt.step}</Tag>
                </>
              )}
            </Typography.Text>
          ),
          color: SOURCE_COLOR[evt.source] ?? 'gray',
          children: <EventLine event={evt} onReplay={hasFailedActEnd ? setReplayEvent : undefined} />,
        }))}
      />
      <ToolCallReplayModal
        event={replayEvent}
        open={replayEvent !== null}
        onClose={() => setReplayEvent(null)}
      />
    </>
  );
}

function EventLine({ event, onReplay }: { event: TraceEvent; onReplay?: (e: TraceEvent) => void }) {
  const { token } = theme.useToken();
  const summary = summarizeEvent(event, onReplay, {
    fillBg: token.colorFillQuaternary,
    errorBg: token.colorErrorBg,
    successBg: token.colorSuccessBg,
  });
  return (
    <Space direction="vertical" size={2} style={{ width: '100%' }}>
      <Space size={6}>
        <Tag color={SOURCE_COLOR[event.source] ?? 'default'}>{event.type}</Tag>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {event.source}
        </Typography.Text>
      </Space>
      {summary && <div>{summary}</div>}
    </Space>
  );
}

function summarizeEvent(
  event: TraceEvent,
  onReplay: ((e: TraceEvent) => void) | undefined,
  colors: { fillBg: string; errorBg: string; successBg: string },
): ReactNode {
  const data = event.data ?? {};
  if (event.type === 'think_end') {
    const msg = (data as { assistant_message?: { content?: string; tool_calls?: unknown[] } })
      .assistant_message;
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        {msg?.content && (
          <Typography.Paragraph
            style={{ margin: 0, background: colors.fillBg, padding: 8, borderRadius: 4, fontSize: 13 }}
          >
            {msg.content}
          </Typography.Paragraph>
        )}
        {msg?.tool_calls && msg.tool_calls.length > 0 && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {i18n.t('trace:timeline.toolCallsCount', { count: msg.tool_calls.length })}
          </Typography.Text>
        )}
      </Space>
    );
  }
  if (event.type === 'act_end') {
    const results = (data as { tool_results?: Array<{ content?: string; tool_call_id?: string }> })
      .tool_results;
    if (!results) return null;
    const hasError = results.some((r) => (r.content ?? '').startsWith('Error:'));
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        {results.map((r, i) => {
          const isError = (r.content ?? '').startsWith('Error:');
          return (
            <Typography.Paragraph
              key={i}
              style={{
                margin: 0,
                padding: 8,
                borderRadius: 4,
                fontSize: 12,
                background: isError ? colors.errorBg : colors.successBg,
                fontFamily: FONT_MONO,
              }}
            >
              {r.content}
            </Typography.Paragraph>
          );
        })}
        {hasError && onReplay && (
          <Button
            type="link"
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => onReplay(event)}
            style={{ padding: 0, fontSize: 11 }}
          >
            {i18n.t('trace:timeline.replayToolCall')}
          </Button>
        )}
      </Space>
    );
  }
  if (event.type === 'act_start') {
    const calls = (data as { tool_calls?: Array<{ name?: string; arguments?: unknown }> }).tool_calls;
    if (!calls) return null;
    return (
      <Space direction="vertical" size={2} style={{ width: '100%' }}>
        {calls.map((c, i) => (
          <Typography.Text key={i} style={{ fontSize: 12 }}>
            <Tag color="geekblue">{c.name}</Tag>
            <code>{JSON.stringify(c.arguments)}</code>
          </Typography.Text>
        ))}
      </Space>
    );
  }
  if (event.type === 'run_end' || event.type === 'run_error' || event.type === 'task.finished') {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        <code>{JSON.stringify(data)}</code>
      </Typography.Text>
    );
  }
  if (event.type === 'run_start') {
    const goal = (data as { metadata?: { goal?: string } }).metadata?.goal;
    return goal ? <Typography.Text>{goal}</Typography.Text> : null;
  }
  return null;
}
