import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  theme,
} from 'antd';
import { ArrowLeftOutlined, FileSearchOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';
import { useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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

      <Row gutter={[20, 20]}>
          <Col xs={24} lg={9}>
            <PageCard
              title={
                <PageCardTitle
                  icon={
                    <PageCardIcon color={token.colorPrimary} bg={token.colorPrimaryBg}>
                      <FileSearchOutlined />
                    </PageCardIcon>
                  }
                >
                  {t('taskStateMachine')}
                </PageCardTitle>
              }
              styles={{ body: { padding: '16px 20px' } }}
            >
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="trace_id">
                  <code style={{ fontSize: 12 }}>{detail.trace_id}</code>
                </Descriptions.Item>
                <Descriptions.Item label="task_name">{detail.task_name}</Descriptions.Item>
                <Descriptions.Item label={t('bizDate')}>{detail.date_string}</Descriptions.Item>
                <Descriptions.Item label={t('startTime')}>{formatTimestamp(detail.start_timestamp)}</Descriptions.Item>
                <Descriptions.Item label={t('endTime')}>{formatTimestamp(detail.finish_timestamp)}</Descriptions.Item>
                <Descriptions.Item label={t('output')}>
                  <DataDisplay data={detail.data} />
                </Descriptions.Item>
              </Descriptions>
            </PageCard>
          </Col>

          <Col xs={24} lg={15}>
            <PageCard
              title={
                <PageCardTitle
                  icon={
                    <PageCardIcon color="#32ade6" bg="rgba(50,173,230,0.12)">
                      <SwapOutlined />
                    </PageCardIcon>
                  }
                >
                  {t('agentTrace')}
                </PageCardTitle>
              }
              extra={
                agent != null ? (
                  <Space size={[6, 0]} wrap>
                    {agent.stop_reason ? <Tag color="purple">stop_reason: {agent.stop_reason}</Tag> : null}
                    {agent.total_steps != null ? <Tag color="blue">{agent.total_steps} steps</Tag> : null}
                    {agent.tool_calls_count != null ? <Tag color="cyan">{agent.tool_calls_count} tools</Tag> : null}
                    {agent.token_usage?.total != null ? <Tag>tokens: {agent.token_usage.total}</Tag> : null}
                    {agent.duration_seconds != null ? <Tag>{formatSeconds(agent.duration_seconds)}</Tag> : null}
                  </Space>
                ) : null
              }
              styles={{ body: { padding: '16px 20px' } }}
            >
              {agent?.goal ? (
                <Alert
                  type="info"
                  showIcon={false}
                  message={<Typography.Text strong>goal</Typography.Text>}
                  description={agent.goal}
                  style={{ marginBottom: 12 }}
                />
              ) : null}
              {agent?.final_answer ? (
                <Card
                  size="small"
                  title="final_answer"
                  style={{ marginBottom: 12 }}
                >
                  <div className="markdown-body" style={{ fontSize: 13 }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {String(agent.final_answer)}
                    </ReactMarkdown>
                  </div>
                </Card>
              ) : null}

              <TraceView events={traceEvents ?? []} />
            </PageCard>
          </Col>
        </Row>
        <CompareView
          traceId={traceId || null}
          open={replayOpen}
          onClose={() => setReplayOpen(false)}
        />
    </PageShell>
  );
}

function DataDisplay({ data }: { data: unknown }) {
  if (!data) return <Typography.Text type="secondary">—</Typography.Text>;

  if (typeof data === 'object' && data !== null) {
    const d = data as Record<string, unknown>;
    const content = d.content;
    if (typeof content === 'string' && content.length > 0) {
      return (
        <div style={{ maxHeight: 400, overflow: 'auto' }}>
          <div className="markdown-body" style={{ fontSize: 12 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        </div>
      );
    }
  }

  try {
    const json = JSON.stringify(data, null, 2);
    return (
      <pre style={{ margin: 0, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
        {json}
      </pre>
    );
  } catch {
    return <Typography.Text type="secondary">[无法序列化]</Typography.Text>;
  }
}
