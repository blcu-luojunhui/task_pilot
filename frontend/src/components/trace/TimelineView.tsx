import { Timeline, Tag, Typography, Space, Alert } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useTranslation } from 'react-i18next';
import i18n from '@/locales/i18n';
import type { TraceEvent } from '@/api/types';
import { formatIso } from '@/utils/format';
import { SOURCE_COLOR } from '@/utils/colors';

export function TimelineView({ events }: { events: TraceEvent[] }) {
  const { t } = useTranslation('trace');

  if (events.length === 0) {
    return <Alert type="warning" showIcon message={t('timeline.noEvents')} />;
  }

  return (
    <div>
      <style>{`.ant-timeline-item-label{width:152px!important;flex:none!important;padding-inline-end:4px!important}.ant-timeline-item-content{left:156px!important;width:calc(100% - 166px)!important}.ant-timeline-item-tail,.ant-timeline-item-head{left:156px!important}`}</style>
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
        children: <EventLine event={evt} />,
      }))}
    />
    </div>
  );
}

function EventLine({ event }: { event: TraceEvent }) {
  const summary = summarizeEvent(event);
  return (
    <Space direction="vertical" size={2} style={{ width: '100%' }}>
      <Space size={6}>
        <Tag color={SOURCE_COLOR[event.source] ?? 'default'}>{event.type}</Tag>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {event.source}
        </Typography.Text>
      </Space>
      {summary && (
        <div className="markdown-body" style={{ fontSize: 12 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{summary}</ReactMarkdown>
        </div>
      )}
    </Space>
  );
}

function summarizeEvent(event: TraceEvent): string | null {
  const data = event.data ?? {};
  if (event.type === 'think_end') {
    const msg = (data as { assistant_message?: { content?: string; tool_calls?: unknown[] } })
      .assistant_message;
    const parts: string[] = [];
    if (msg?.content) parts.push(msg.content);
    if (msg?.tool_calls && msg.tool_calls.length > 0) {
      parts.push(`*${i18n.t('trace:timeline.toolCallsCount', { count: msg.tool_calls.length })}*`);
    }
    return parts.join('\n\n');
  }
  if (event.type === 'act_end') {
    const results = (data as { tool_results?: Array<{ content?: string; tool_call_id?: string }> })
      .tool_results;
    if (!results) return null;
    return results.map((r) => r.content || '').join('\n\n');
  }
  if (event.type === 'act_start') {
    const calls = (data as { tool_calls?: Array<{ name?: string; arguments?: unknown }> }).tool_calls;
    if (!calls) return null;
    return calls.map((c) =>
      `**${c.name}** \`${JSON.stringify(c.arguments)}\``
    ).join('\n');
  }
  if (event.type === 'run_end' || event.type === 'run_error' || event.type === 'task.finished') {
    return ['```json', JSON.stringify(data, null, 2), '```'].join('\n');
  }
  if (event.type === 'run_start') {
    const goal = (data as { metadata?: { goal?: string } }).metadata?.goal;
    return goal || null;
  }
  return null;
}
