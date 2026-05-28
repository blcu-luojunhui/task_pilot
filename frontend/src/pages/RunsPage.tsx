import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Button,
  Drawer,
  Descriptions,
  Statistic,
  Row,
  Col,
} from 'antd';
import { SearchOutlined, ReloadOutlined, HistoryOutlined, SwapOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { listRuns } from '@/api/runs';
import { CompareView } from '@/components/replay/CompareView';
import type { RunSummary } from '@/api/types';

const SUCCESS_OPTIONS = [
  { value: 1, label: '成功' },
  { value: 0, label: '失败' },
];

export function RunsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<RunSummary | null>(null);
  const [replayTraceId, setReplayTraceId] = useState<string | null>(null);
  const [filterForm] = Form.useForm<{ success?: number; goal_keyword?: string }>();

  const fetch = async (p: number = page) => {
    setLoading(true);
    try {
      const v = filterForm.getFieldsValue();
      const data = await listRuns({
        page: p,
        page_size: 20,
        success: v.success,
        goal_keyword: v.goal_keyword?.trim() || undefined,
      });
      setItems(data.items);
      setTotal(data.total);
      setPage(p);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns = [
    {
      title: 'Trace',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 170,
      render: (v: string) => (
        <Typography.Link onClick={() => navigate(`/tasks/${encodeURIComponent(v)}`)}>
          <code style={{ fontSize: 11 }}>{v.slice(-20)}</code>
        </Typography.Link>
      ),
    },
    {
      title: '状态',
      dataIndex: 'success',
      key: 'success',
      width: 60,
      render: (v: number) =>
        v ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag>,
    },
    {
      title: 'Goal',
      dataIndex: 'goal',
      key: 'goal',
      ellipsis: true,
      render: (v: string) => (
        <Typography.Text style={{ fontSize: 12 }} ellipsis>
          {v}
        </Typography.Text>
      ),
    },
    {
      title: 'Stop Reason',
      dataIndex: 'stop_reason',
      key: 'stop_reason',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Steps',
      dataIndex: 'total_steps',
      key: 'total_steps',
      width: 60,
      align: 'center' as const,
    },
    {
      title: 'Tools',
      dataIndex: 'tool_calls_count',
      key: 'tool_calls_count',
      width: 60,
      align: 'center' as const,
    },
    {
      title: 'Tokens',
      key: 'tokens',
      width: 80,
      align: 'right' as const,
      render: (_: unknown, r: RunSummary) =>
        r.token_usage ? (
          <Typography.Text style={{ fontSize: 11 }}>
            {r.token_usage.total.toLocaleString()}
          </Typography.Text>
        ) : (
          '-'
        ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (v: string) => (
        <Typography.Text style={{ fontSize: 11 }}>{v}</Typography.Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, r: RunSummary) => (
        <Button
          type="link"
          size="small"
          icon={<SwapOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            setReplayTraceId(r.trace_id);
          }}
        >
          Replay
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <HistoryOutlined /> Runs 运行历史
      </Typography.Title>
      <Typography.Text type="secondary">
        Agent 每次完整运行后由 ContinuousImprovement 落库。可对比不同 run 的 token 消耗、步骤数、工具调用成功率。
      </Typography.Text>

      <Card variant="borderless">
        <Form layout="inline" form={filterForm} onFinish={() => fetch(1)}>
          <Form.Item name="success" label="状态">
            <Select
              placeholder="全部"
              allowClear
              style={{ width: 100 }}
              options={SUCCESS_OPTIONS}
            />
          </Form.Item>
          <Form.Item name="goal_keyword" label="Goal">
            <Input placeholder="关键词" allowClear style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} htmlType="submit">
                筛选
              </Button>
              <Button
                onClick={() => {
                  filterForm.resetFields();
                  fetch(1);
                }}
              >
                重置
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => fetch(page)}>
                刷新
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card variant="borderless" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          dataSource={items}
          columns={columns}
          loading={loading}
          size="middle"
          onRow={(record: RunSummary) => ({
            onClick: () => setDetail(record),
            style: { cursor: 'pointer' },
          })}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => fetch(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      </Card>

      {/* Run 详情 Drawer */}
      <Drawer
        title={
          <Space>
            <HistoryOutlined />
            <span>Run 详情</span>
            {detail && (
              <Tag color={detail.success ? 'green' : 'red'}>
                {detail.success ? '成功' : '失败'}
              </Tag>
            )}
          </Space>
        }
        open={detail !== null}
        onClose={() => setDetail(null)}
        width={600}
      >
        {detail && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="trace_id">
                <Typography.Link
                  onClick={() => navigate(`/tasks/${encodeURIComponent(detail.trace_id)}`)}
                >
                  <code>{detail.trace_id}</code>
                </Typography.Link>
              </Descriptions.Item>
              <Descriptions.Item label="stop_reason">
                <Tag>{detail.stop_reason}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="时间">{detail.created_at}</Descriptions.Item>
            </Descriptions>

            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="Steps" value={detail.total_steps} />
              </Col>
              <Col span={8}>
                <Statistic title="Tool Calls" value={detail.tool_calls_count} />
              </Col>
              <Col span={8}>
                <Statistic
                  title="Tokens"
                  value={detail.token_usage?.total ?? 0}
                />
              </Col>
            </Row>

            {detail.token_usage && (
              <div>
                <Typography.Text strong>Token 分布</Typography.Text>
                <pre style={{ fontSize: 11, marginTop: 4 }}>
                  prompt: {detail.token_usage.prompt.toLocaleString()}
                  {'\n'}completion: {detail.token_usage.completion.toLocaleString()}
                  {'\n'}total: {detail.token_usage.total.toLocaleString()}
                </pre>
              </div>
            )}

            <div>
              <Typography.Text strong>Goal</Typography.Text>
              <Typography.Paragraph style={{ marginTop: 4, background: '#fafafa', padding: 8, borderRadius: 4 }}>
                {detail.goal}
              </Typography.Paragraph>
            </div>

            {detail.final_answer && (
              <div>
                <Typography.Text strong>Final Answer</Typography.Text>
                <Typography.Paragraph style={{ marginTop: 4, background: '#f6ffed', padding: 8, borderRadius: 4 }}>
                  {detail.final_answer}
                </Typography.Paragraph>
              </div>
            )}

            {detail.failed_tool_calls && detail.failed_tool_calls.length > 0 && (
              <div>
                <Typography.Text strong type="danger">
                  失败的工具调用 ({detail.failed_tool_calls.length})
                </Typography.Text>
                <pre style={{ fontSize: 11, marginTop: 4, background: '#fff2f0', padding: 8, borderRadius: 4 }}>
                  {JSON.stringify(detail.failed_tool_calls, null, 2)}
                </pre>
              </div>
            )}
          </Space>
        )}
      </Drawer>
      <CompareView
        traceId={replayTraceId}
        open={replayTraceId !== null}
        onClose={() => setReplayTraceId(null)}
      />
    </Space>
  );
}
