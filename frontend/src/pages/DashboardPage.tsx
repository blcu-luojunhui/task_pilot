import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Card, Col, Row, Space, Statistic, Table, Tag, Typography, theme } from 'antd';
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

const STAT_CARD_STYLE: Record<string, React.CSSProperties> = {
  running: {
    borderLeft: '3px solid #722ed1',
    borderRadius: 10,
  },
  success: {
    borderLeft: '3px solid #52c41a',
    borderRadius: 10,
  },
  failed: {
    borderLeft: '3px solid #ff4d4f',
    borderRadius: 10,
  },
  cancelled: {
    borderLeft: '3px solid #faad14',
    borderRadius: 10,
  },
};

export function DashboardPage() {
  const { t } = useTranslation('dashboard');
  const { token } = theme.useToken();
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
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Dashboard
        </Typography.Title>
        <Typography.Text type="secondary">{t('subtitle')}</Typography.Text>
      </div>

      <Card variant="borderless" loading={loading} style={{ borderRadius: 10 }}>
        <Space size={32} wrap>
          <HealthBadge label={t('health.mysql')} flag={stats?.health.mysql ?? '-'} />
          <HealthBadge label={t('health.logService')} flag={stats?.health.log_service ?? '-'} />
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card style={STAT_CARD_STYLE.running}>
            <Statistic
              title={t('running')}
              value={stats?.counts.running ?? 0}
              prefix={<ThunderboltFilled style={{ color: '#722ed1', fontSize: 20 }} />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card style={STAT_CARD_STYLE.success}>
            <Statistic
              title={t('success24h')}
              value={stats?.counts.success_24h ?? 0}
              prefix={<CheckCircleFilled style={{ color: '#52c41a', fontSize: 20 }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card style={STAT_CARD_STYLE.failed}>
            <Statistic
              title={t('failed24h')}
              value={stats?.counts.failed_24h ?? 0}
              prefix={<CloseCircleFilled style={{ color: '#ff4d4f', fontSize: 20 }} />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card style={STAT_CARD_STYLE.cancelled}>
            <Statistic
              title={t('cancelled24h')}
              value={stats?.counts.cancelled_24h ?? 0}
              prefix={<ExclamationCircleFilled style={{ color: '#faad14', fontSize: 20 }} />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={t('throughputTitle')}
        variant="borderless"
        style={{ borderRadius: 10 }}
      >
        {stats?.throughput_24h && stats.throughput_24h.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={stats.throughput_24h}>
              <CartesianGrid strokeDasharray="3 3" stroke={token.colorBorderSecondary} />
              <XAxis dataKey="hour" style={{ fontSize: 11 }} tick={{ fill: token.colorTextSecondary }} />
              <YAxis allowDecimals={false} style={{ fontSize: 11 }} tick={{ fill: token.colorTextSecondary }} />
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: `1px solid ${token.colorBorderSecondary}`,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="success"
                name={t('successLine')}
                stroke="#52c41a"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="failed"
                name={t('failedLine')}
                stroke="#ff4d4f"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <Typography.Text type="secondary">{t('no24hData')}</Typography.Text>
        )}
      </Card>

      <Card
        title={t('recentFailures')}
        variant="borderless"
        style={{ borderRadius: 10 }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          rowKey="trace_id"
          dataSource={stats?.recent_failures ?? []}
          loading={loading}
          pagination={false}
          size="middle"
          style={{ borderRadius: 10 }}
          columns={[
            {
              title: t('columnStatus'),
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
            { title: t('columnTaskName'), dataIndex: 'task_name' },
            { title: t('columnStartTime'), dataIndex: 'start_timestamp', render: (v) => formatTimestamp(v) },
            { title: t('columnError'), dataIndex: 'error', ellipsis: true },
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
      <Badge
        color={
          color === 'green'
            ? '#52c41a'
            : color === 'orange'
              ? '#faad14'
              : color === 'red'
                ? '#ff4d4f'
                : '#d9d9d9'
        }
      />
      <Typography.Text strong>{label}</Typography.Text>
      <Tag color={color}>{flag.toUpperCase()}</Tag>
    </Space>
  );
}
