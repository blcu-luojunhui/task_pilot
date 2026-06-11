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
import { useTranslation } from 'react-i18next';
import type { RunSummary } from '@/api/types';

export function RunsPage() {
  const { t } = useTranslation('runs');
  const navigate = useNavigate();
  const [items, setItems] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<RunSummary | null>(null);
  const [replayTraceId, setReplayTraceId] = useState<string | null>(null);
  const [filterForm] = Form.useForm<{ success?: number; goal_keyword?: string }>();

  const successOptions = [
    { value: 1, label: t('success') },
    { value: 0, label: t('failed') },
  ];

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
      title: t('columnTrace'),
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
      title: t('columnStatus'),
      dataIndex: 'success',
      key: 'success',
      width: 60,
      render: (v: number) =>
        v ? <Tag color="green">{t('success')}</Tag> : <Tag color="red">{t('failed')}</Tag>,
    },
    {
      title: t('columnGoal'),
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
      title: t('columnStopReason'),
      dataIndex: 'stop_reason',
      key: 'stop_reason',
      width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: t('columnSteps'),
      dataIndex: 'total_steps',
      key: 'total_steps',
      width: 60,
      align: 'center' as const,
    },
    {
      title: t('columnTools'),
      dataIndex: 'tool_calls_count',
      key: 'tool_calls_count',
      width: 60,
      align: 'center' as const,
    },
    {
      title: t('columnTokens'),
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
      title: t('columnTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (v: string) => (
        <Typography.Text style={{ fontSize: 11 }}>{v}</Typography.Text>
      ),
    },
    {
      title: t('columnActions'),
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
          {t('replay')}
        </Button>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <HistoryOutlined /> {t('title')}
      </Typography.Title>
      <Typography.Text type="secondary">
        {t('subtitle')}
      </Typography.Text>

      <Card variant="borderless">
        <Form layout="inline" form={filterForm} onFinish={() => fetch(1)}>
          <Form.Item name="success" label={t('columnStatus')}>
            <Select
              placeholder={t('statusAll')}
              allowClear
              style={{ width: 100 }}
              options={successOptions}
            />
          </Form.Item>
          <Form.Item name="goal_keyword" label={t('columnGoal')}>
            <Input placeholder={t('columnGoal')} allowClear style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} htmlType="submit">
                {t('filter')}
              </Button>
              <Button
                onClick={() => {
                  filterForm.resetFields();
                  fetch(1);
                }}
              >
                {t('reset')}
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => fetch(page)}>
                {t('refresh')}
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
            showTotal: (count) => t('totalCount', { count }),
          }}
        />
      </Card>

      {/* Run 详情 Drawer */}
      <Drawer
        title={
          <Space>
            <HistoryOutlined />
            <span>{t('detailTitle')}</span>
            {detail && (
              <Tag color={detail.success ? 'green' : 'red'}>
                {detail.success ? t('success') : t('failed')}
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
              <Descriptions.Item label={t('detailTime')}>{detail.created_at}</Descriptions.Item>
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
                <Typography.Text strong>{t('tokenDistribution')}</Typography.Text>
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
                  {t('failedToolCalls', { n: detail.failed_tool_calls.length })}
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
