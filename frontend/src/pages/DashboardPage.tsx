import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Col, Row, Space, Statistic, Table, Tag, Typography, theme } from 'antd';
import {
  CheckCircleFilled,
  CloseCircleFilled,
  DashboardOutlined,
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
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';
import { useNavigate } from 'react-router-dom';
import { formatTimestamp, truncateTraceId } from '@/utils/format';
import { useSemanticColors } from '@/hooks/useSemanticColors';

export function DashboardPage() {
  const { t } = useTranslation('dashboard');
  const { token } = theme.useToken();
  const palette = useSemanticColors();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const controller = new AbortController();
    let mounted = true;

    const refresh = async () => {
      setLoading(true);
      try {
        const data = await getSystemStats({ signal: controller.signal });
        if (mounted) setStats(data);
      } catch {
        // 取消或网络错误静默
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => {
      mounted = false;
      controller.abort();
      window.clearInterval(id);
    };
  }, []);

  const statCards = [
    { key: 'running', title: t('running'), value: stats?.counts.running ?? 0, icon: ThunderboltFilled, color: palette.chartAccent },
    { key: 'success', title: t('success24h'), value: stats?.counts.success_24h ?? 0, icon: CheckCircleFilled, color: palette.chartSuccess },
    { key: 'failed', title: t('failed24h'), value: stats?.counts.failed_24h ?? 0, icon: CloseCircleFilled, color: palette.chartError },
    { key: 'cancelled', title: t('cancelled24h'), value: stats?.counts.cancelled_24h ?? 0, icon: ExclamationCircleFilled, color: palette.chartWarning },
  ] as const;

  return (
    <PageShell>
      <PageHero
        title={t('title')}
        subtitle={t('subtitle')}
        icon={<DashboardOutlined />}
        gradient="cyan"
      />

      <Row gutter={[20, 20]}>
        <Col span={24}>
          <PageCard loading={loading} styles={{ body: { padding: '20px 24px' } }}>
            <Space size={32} wrap>
              <HealthBadge label={t('health.mysql')} flag={stats?.health.mysql ?? '-'} />
              <HealthBadge label={t('health.logService')} flag={stats?.health.log_service ?? '-'} />
            </Space>
          </PageCard>
        </Col>

        {statCards.map((card) => (
          <Col xs={12} md={6} key={card.key}>
            <PageCard styles={{ body: { padding: '18px 20px' } }}>
              <Statistic
                title={card.title}
                value={card.value}
                prefix={<card.icon style={{ color: card.color, fontSize: 20 }} />}
                valueStyle={{ color: card.color, fontWeight: 600, letterSpacing: '-0.02em' }}
              />
            </PageCard>
          </Col>
        ))}

        <Col span={24}>
          <PageCard
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color={palette.chartAccent} bg={token.colorPrimaryBg}>
                    <ThunderboltFilled />
                  </PageCardIcon>
                }
              >
                {t('throughputTitle')}
              </PageCardTitle>
            }
            styles={{ body: { padding: '20px 24px' } }}
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
                  <Line type="monotone" dataKey="success" name={t('successLine')} stroke={palette.chartSuccess} strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="failed" name={t('failedLine')} stroke={palette.chartError} strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Typography.Text type="secondary">{t('no24hData')}</Typography.Text>
            )}
          </PageCard>
        </Col>

        <Col span={24}>
          <PageCard
            table
            title={
              <PageCardTitle
                icon={
                  <PageCardIcon color={palette.chartError} bg={token.colorErrorBg}>
                    <CloseCircleFilled />
                  </PageCardIcon>
                }
              >
                {t('recentFailures')}
              </PageCardTitle>
            }
            styles={{ body: { padding: 0 } }}
          >
            <Table
              rowKey="trace_id"
              dataSource={stats?.recent_failures ?? []}
              loading={loading}
              pagination={false}
              size="middle"
              columns={[
                { title: t('columnStatus'), dataIndex: 'task_status', width: 90, render: (s) => <TaskStatusTag status={s} /> },
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
          </PageCard>
        </Col>
      </Row>
    </PageShell>
  );
}

function HealthBadge({ label, flag }: { label: string; flag: string }) {
  const palette = useSemanticColors();
  const color =
    flag === 'ok' ? 'green' : flag === 'degraded' ? 'orange' : flag === 'failed' ? 'red' : 'default';
  const dotColor =
    color === 'green'
      ? palette.chartSuccess
      : color === 'orange'
        ? palette.chartWarning
        : color === 'red'
          ? palette.chartError
          : palette.chartNeutral;
  return (
    <Space>
      <Badge color={dotColor} />
      <Typography.Text strong>{label}</Typography.Text>
      <Tag color={color}>{flag.toUpperCase()}</Tag>
    </Space>
  );
}
