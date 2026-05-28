import { useEffect, useState } from 'react';
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
} from 'antd';
import { ArrowLeftOutlined, ReloadOutlined, SwapOutlined } from '@ant-design/icons';
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

const STREAM_STATUS_MAP: Record<StreamStatus, { text: string; color: 'green' | 'blue' | 'red' | 'orange' | 'default' }> = {
  idle: { text: '未连接', color: 'default' },
  connecting: { text: '连接中...', color: 'blue' },
  open: { text: '实时同步中', color: 'green' },
  closed: { text: '已结束', color: 'default' },
  error: { text: '重连中...', color: 'orange' },
};

export function TaskDetailPage() {
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

  const refresh = async () => {
    if (!traceId) return;
    setDetailLoading(true);
    try {
      const [d] = await Promise.all([getTaskDetail(traceId), traceOpen(traceId)]);
      setDetail(d);
    } catch {
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

  if (loading && !detail) {
    return <Spin />;
  }
  if (!detail) {
    return (
      <Alert
        type="error"
        showIcon
        message="任务不存在或已被清理"
        description={`trace_id: ${traceId}`}
      />
    );
  }

  const agent = detail.agent_metadata;
  const streamMeta = STREAM_STATUS_MAP[streamStatus];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            返回
          </Button>
          <Typography.Title level={4} style={{ margin: 0 }}>
            任务详情
          </Typography.Title>
          <TaskStatusTag status={detail.task_status} />
          {isLive && (
            <Badge
              status={
                streamMeta.color === 'orange'
                  ? 'processing'
                  : (streamMeta.color === 'green' ? 'success' : 'default')
              }
              text={streamMeta.text}
            />
          )}
        </Space>
        <Space>
          <Button
            icon={<SwapOutlined />}
            onClick={() => setReplayOpen(true)}
            disabled={!detail}
          >
            Time Travel
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={refresh}
            loading={detailLoading || traceLoading}
          >
            刷新
          </Button>
        </Space>
      </Space>

      <Row gutter={16}>
        {/* 左侧：任务状态机 */}
        <Col xs={24} lg={9}>
          <Card title="任务状态机" variant="borderless">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="trace_id">
                <code style={{ fontSize: 12 }}>{detail.trace_id}</code>
              </Descriptions.Item>
              <Descriptions.Item label="task_name">{detail.task_name}</Descriptions.Item>
              <Descriptions.Item label="业务日期">{detail.date_string}</Descriptions.Item>
              <Descriptions.Item label="开始">{formatTimestamp(detail.start_timestamp)}</Descriptions.Item>
              <Descriptions.Item label="结束">{formatTimestamp(detail.finish_timestamp)}</Descriptions.Item>
              <Descriptions.Item label="输出结果">
                <DataDisplay data={detail.data} />
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>

        {/* 右侧：Agent 流程追溯 */}
        <Col xs={24} lg={15}>
          <Card
            title="Agent 流程追溯"
            extra={
              agent && (
                <Space size={[6, 0]} wrap>
                  <Tag color="purple">stop_reason: {agent.stop_reason}</Tag>
                  <Tag color="blue">{agent.total_steps} steps</Tag>
                  <Tag color="cyan">{agent.tool_calls_count} tools</Tag>
                  <Tag>tokens: {agent.token_usage.total}</Tag>
                  <Tag>{formatSeconds(agent.duration_seconds)}</Tag>
                </Space>
              )
            }
            variant="borderless"
          >
            {agent?.goal && (
              <Alert
                type="info"
                showIcon={false}
                message={<Typography.Text strong>goal</Typography.Text>}
                description={agent.goal}
                style={{ marginBottom: 12 }}
              />
            )}
            {agent?.final_answer && (
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
            )}

            <TraceView events={traceEvents} />
          </Card>
        </Col>
      </Row>
      <CompareView
        traceId={traceId || null}
        open={replayOpen}
        onClose={() => setReplayOpen(false)}
      />
    </Space>
  );
}

function DataDisplay({ data }: { data: unknown }) {
  if (!data) return <Typography.Text type="secondary">—</Typography.Text>;

  // run_goal 任务结果：data 包含 {content, goal, ...}
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

  // fallback: 原始 JSON
  return (
    <pre style={{ margin: 0, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
