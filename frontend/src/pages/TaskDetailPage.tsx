import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Badge,
  Button,
  Card,
  Space,
  Spin,
  Tag,
  Typography,
  theme,
} from 'antd';
import { AimOutlined, ArrowLeftOutlined, FileSearchOutlined, PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';
import { useNavigate, useParams } from 'react-router-dom';
import { MarkdownContent } from '@/components/chat/MarkdownContent';
import { getTaskDetail } from '@/api/tasks';
import type { TaskDetail } from '@/api/types';
import { TaskStatus } from '@/api/types';
import { TaskStatusTag } from '@/components/task/TaskStatusTag';
import { TraceView } from '@/components/trace/TraceView';
import { CompareView } from '@/components/replay/CompareView';
import { useTraceStore } from '@/stores/traceStore';
import { useTraceStream, type StreamStatus } from '@/hooks/useTraceStream';
import { formatSeconds, formatTimestamp } from '@/utils/format';
import '@/components/chat/ChatMessage.css';

const STREAM_STATUS_COLORS: Record<StreamStatus, 'green' | 'blue' | 'red' | 'orange' | 'default'> = {
  idle: 'default',
  connecting: 'blue',
  open: 'green',
  closed: 'default',
  error: 'orange',
};

export function TaskDetailPage() {
  const { token } = theme.useToken();
  const { t } = useTranslation('tasks');
  const { traceId = '' } = useParams<{ traceId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [replayOpen, setReplayOpen] = useState(false);

  const traceEvents = useTraceStore((s) => s.events);
  const traceLoading = useTraceStore((s) => s.loading);
  const traceOpen = useTraceStore((s) => s.open);
  const frozen = useTraceStore((s) => s.frozen);
  const setFrozen = useTraceStore((s) => s.setFrozen);

  const isLive =
    detail?.task_status === TaskStatus.PROCESSING ||
    detail?.task_status === TaskStatus.CANCEL_REQUESTED;
  const streamStatus = useTraceStream(traceId || null, { enabled: isLive });

  const streamStatusText = useMemo<Record<StreamStatus, string>>(
    () => ({
      idle: t('streamIdle'),
      connecting: t('streamConnecting'),
      open: t('streamOpen'),
      closed: t('streamClosed'),
      error: t('streamError'),
    }),
    [t],
  );

  const refresh = async () => {
    if (!traceId) return;
    setDetailLoading(true);
    try {
      const [d] = await Promise.all([getTaskDetail(traceId), traceOpen(traceId)]);
      setDetail(d);
    } catch (err) {
      console.error('[TaskDetailPage] refresh failed:', err);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [traceId]);

  const prevStreamStatus = useRef(streamStatus);
  useEffect(() => {
    if (prevStreamStatus.current === 'open' && streamStatus === 'closed') {
      refresh();
    }
    prevStreamStatus.current = streamStatus;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamStatus]);

  const loading = (detailLoading && !detail) || traceLoading;

  // 所有 hooks 必须在条件 return 之前调用
  const agent = detail?.agent_metadata;
  const streamColor = STREAM_STATUS_COLORS[streamStatus];

  if (loading && !detail) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" tip={t('loading') || 'Loading...'} />
      </div>
    );
  }
  if (!detail) {
    return (
      <Alert
        type="error"
        showIcon
        message={t('taskNotExist')}
        description={`trace_id: ${traceId}`}
        action={
          <Button size="small" onClick={() => navigate(-1)}>
            {t('back')}
          </Button>
        }
      />
    );
  }

  return (
    <PageShell>
      <PageHero
        title={t('taskDetail')}
        subtitle={detail.trace_id}
        icon={<FileSearchOutlined />}
        gradient="purple"
        extra={
          <Space wrap>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
              {t('back')}
            </Button>
            <TaskStatusTag status={detail.task_status} />
            {isLive && (
              <>
                <Badge
                  status={
                    streamColor === 'orange'
                      ? 'processing'
                      : streamColor === 'green'
                        ? 'success'
                        : 'default'
                  }
                  text={streamStatusText[streamStatus]}
                />
                <Button
                  icon={frozen ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                  onClick={() => setFrozen(!frozen)}
                  type={frozen ? 'primary' : 'default'}
                  danger={frozen}
                >
                  {frozen ? t('resume') : t('freeze')}
                </Button>
              </>
            )}
            <Button icon={<SwapOutlined />} onClick={() => setReplayOpen(true)} disabled={!detail}>
              Time Travel
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={refresh}
              loading={detailLoading || traceLoading}
            >
              {t('refresh')}
            </Button>
          </Space>
        }
      />

      <div style={{ display: 'flex', gap: 16, marginTop: 16 }}>
        {/* ═══ 左栏：Goal + 输出 + 追溯 ═══ */}
        <div style={{ flex: 8, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Goal */}
          {agent?.goal && (
            <Card
              size="small"
              title={
                <Space size={4}>
                  <AimOutlined style={{ color: token.colorPrimary }} />
                  <span>Goal</span>
                </Space>
              }
              styles={{ body: { padding: '10px 16px' } }}
            >
              <div style={{ fontSize: 13, color: token.colorText, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {agent.goal}
              </div>
            </Card>
          )}

          {/* 输出结果 */}
          <Card
            size="small"
            title={<Typography.Text strong style={{ fontSize: 14 }}>{t('output')}</Typography.Text>}
            styles={{ body: { padding: '12px 16px' } }}
          >
            <OutputBlock data={detail.data} agent_metadata={detail.agent_metadata} />
          </Card>

          {/* Agent 流程追溯 */}
          <PageCard
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color="var(--n2)" bg="rgba(23,23,23,0.06)">
                    <SwapOutlined />
                  </PageCardIcon>
                }
              >
                {t('agentTrace')}
              </PageCardTitle>
            }
            styles={{ body: { padding: '12px 16px' } }}
          >
            <TraceView events={traceEvents ?? []} />
          </PageCard>
        </div>

        {/* ═══ 右栏：任务状态机 ═══ */}
        <div style={{ flex: 2, minWidth: 240 }}>
          <div style={{ position: 'sticky', top: 16 }}>
            <Card
              size="small"
              title={
                <Space size={4}>
                  <FileSearchOutlined style={{ color: token.colorPrimary }} />
                  <span>{t('taskStateMachine')}</span>
                </Space>
              }
              styles={{ body: { padding: '12px' } }}
            >
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                {/* 状态 + 基本信息 */}
                <div>
                  <div style={{ marginBottom: 4 }}>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>Status</Typography.Text>
                  </div>
                  <Space size={4}>
                    <TaskStatusTag status={detail.task_status} />
                    {agent?.stop_reason && <Tag color="purple">{agent.stop_reason}</Tag>}
                  </Space>
                </div>

                {/* trace_id */}
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>Trace ID</Typography.Text>
                  <div>
                    <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{detail.trace_id}</code>
                  </div>
                </div>

                {/* 时间信息 */}
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>Timeline</Typography.Text>
                  <div style={{ fontSize: 12, marginTop: 2 }}>
                    <div>Start: {formatTimestamp(detail.start_timestamp) || '—'}</div>
                    <div>End: {formatTimestamp(detail.finish_timestamp) || '—'}</div>
                    {detail.start_timestamp && detail.finish_timestamp && (
                      <Tag color="green" style={{ marginTop: 2 }}>
                        {formatSeconds(detail.finish_timestamp - detail.start_timestamp)}
                      </Tag>
                    )}
                  </div>
                </div>

                {/* Agent 运行指标 */}
                <div>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>Agent Metrics</Typography.Text>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                    {agent?.total_steps != null && <Tag color="blue">{agent.total_steps} steps</Tag>}
                    {agent?.tool_calls_count != null && <Tag color="cyan">{agent.tool_calls_count} tools</Tag>}
                    {agent?.duration_seconds != null && <Tag color="green">{formatSeconds(agent.duration_seconds)}</Tag>}
                  </div>
                </div>

                {/* Token 明细 */}
                {agent?.token_usage?.total != null && (
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>Tokens</Typography.Text>
                    <div style={{ display: 'flex', gap: 4, marginTop: 4, fontSize: 11 }}>
                      <span style={{ color: token.colorTextSecondary }}>prompt:</span>
                      <span>{(agent.token_usage.prompt ?? 0).toLocaleString()}</span>
                      <span style={{ color: token.colorTextSecondary, marginLeft: 4 }}>completion:</span>
                      <span>{(agent.token_usage.completion ?? 0).toLocaleString()}</span>
                      <span style={{ color: token.colorTextSecondary, marginLeft: 4 }}>total:</span>
                      <strong>{agent.token_usage.total.toLocaleString()}</strong>
                    </div>
                  </div>
                )}
              </Space>
            </Card>
          </div>
        </div>
      </div>

      <CompareView
        traceId={traceId || null}
        open={replayOpen}
        onClose={() => setReplayOpen(false)}
      />
    </PageShell>
  );
}

function OutputBlock({ data, agent_metadata }: { data: unknown; agent_metadata: TaskDetail['agent_metadata'] }) {
  const finalAnswer = agent_metadata?.final_answer;
  const rawData = data as Record<string, unknown> | null | undefined;
  const content = typeof rawData?.content === 'string' ? rawData.content : null;
  const tokenUsage = agent_metadata?.token_usage ?? (rawData?.token_usage as Record<string, number> | undefined);
  const toolResults = rawData?.tool_call_results as Array<Record<string, unknown>> | undefined;

  if (!finalAnswer && !content && !rawData) {
    return <Typography.Text type="secondary">—</Typography.Text>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 最终输出 Markdown */}
      {(finalAnswer || content) && (
        <div className="markdown-body" style={{ fontSize: 14, lineHeight: 1.7 }}>
          <MarkdownContent content={String(finalAnswer || content)} />
        </div>
      )}
      {/* 附属信息 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {tokenUsage != null && (
          <Tag>tokens: prompt {tokenUsage.prompt ?? '-'} / completion {tokenUsage.completion ?? '-'} / total {tokenUsage.total ?? '-'}</Tag>
        )}
        {toolResults != null && toolResults.length > 0 && (
          <Tag color="blue">{toolResults.length} tool results</Tag>
        )}
      </div>
    </div>
  );
}
