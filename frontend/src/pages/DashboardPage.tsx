import { useEffect, useState } from 'react';
import { Badge, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  ThunderboltFilled,
} from '@ant-design/icons';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getSystemStats } from '@/api/system';
import type { SystemStats } from '@/api/types';
import { TaskStatusTag } from '@/components/task/TaskStatusTag';
import { useNavigate } from 'react-router-dom';
import { formatTimestamp, truncateTraceId } from '@/utils/format';

export function DashboardPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await getSystemStats();
      setStats(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card variant="borderless" loading={loading}>
        <Space size={24} wrap>
          <HealthBadge label="MySQL" flag={stats?.health.mysql ?? '-'} />
          <HealthBadge label="LogService" flag={stats?.health.log_service ?? '-'} />
        </Space>
      </Card>

      <Row gutter={16}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="运行中"
              value={stats?.counts.running ?? 0}
              prefix={<ThunderboltFilled style={{ color: '#722ed1' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="成功 (24h)"
              value={stats?.counts.success_24h ?? 0}
              prefix={<CheckCircleFilled style={{ color: '#52c41a' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="失败 (24h)"
              value={stats?.counts.failed_24h ?? 0}
              prefix={<CloseCircleFilled style={{ color: '#ff4d4f' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="取消 (24h)"
              value={stats?.counts.cancelled_24h ?? 0}
              prefix={<ExclamationCircleFilled style={{ color: '#faad14' }} />}
            />
          </Card>
        </Col>
      </Row>

      <Card title="24h 吞吐量趋势" variant="borderless">
        {stats?.throughput_24h && stats.throughput_24h.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={stats.throughput_24h}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" style={{ fontSize: 11 }} />
              <YAxis allowDecimals={false} style={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="success"
                name="成功"
                stroke="#52c41a"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="failed"
                name="失败"
                stroke="#ff4d4f"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <Typography.Text type="secondary">暂无 24h 数据</Typography.Text>
        )}
      </Card>

      <Card title="近期失败" variant="borderless">
        <Table
          rowKey="trace_id"
          dataSource={stats?.recent_failures ?? []}
          loading={loading}
          pagination={false}
          size="middle"
          columns={[
            {
              title: '状态',
              dataIndex: 'task_status',
              width: 90,
              render: (s) => <TaskStatusTag status={s} />,
            },
            {
              title: 'trace_id',
              dataIndex: 'trace_id',
              render: (v: string) => (
                <Typography.Link onClick={() => navigate(`/tasks/${encodeURIComponent(v)}`)}>
                  <code>{truncateTraceId(v)}</code>
                </Typography.Link>
              ),
            },
            { title: '任务名', dataIndex: 'task_name' },
            { title: '开始时间', dataIndex: 'start_timestamp', render: (v) => formatTimestamp(v) },
            { title: '错误摘要', dataIndex: 'error', ellipsis: true },
          ]}
        />
      </Card>
    </Space>
  );
}

function HealthBadge({ label, flag }: { label: string; flag: string }) {
  const color =
    flag === 'ok' ? 'green' : flag === 'degraded' ? 'orange' : flag === 'failed' ? 'red' : 'default';
  return (
    <Space>
      <Badge color={color === 'green' ? '#52c41a' : color === 'orange' ? '#faad14' : color === 'red' ? '#ff4d4f' : '#d9d9d9'} />
      <Typography.Text strong>{label}</Typography.Text>
      <Tag color={color}>{flag.toUpperCase()}</Tag>
    </Space>
  );
}
