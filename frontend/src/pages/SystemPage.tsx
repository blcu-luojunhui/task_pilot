import { useEffect, useState } from 'react';
import { Descriptions, Spin, Tag, Typography, theme } from 'antd';
import { MonitorOutlined, LineChartOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { getHealth, type HealthData } from '@/api/system';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';

export function SystemPage() {
  const { t } = useTranslation('system');
  const { token } = theme.useToken();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getHealth()
      .then(setHealth)
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageShell>
      <PageHero
        title={t('title')}
        subtitle={t('description')}
        icon={<MonitorOutlined />}
        gradient="indigo"
      />

      <PageCard
        title={
          <PageCardTitle
            icon={
              <PageCardIcon color={token.colorPrimary} bg={token.colorPrimaryBg}>
                <MonitorOutlined />
              </PageCardIcon>
            }
          >
            {t('healthCheck')}
          </PageCardTitle>
        }
        styles={{ body: { padding: '20px 24px' } }}
      >
        {loading ? (
          <Spin />
        ) : health ? (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label={t('overview')}>
              <Tag color={health.status === 'healthy' ? 'success' : 'error'}>
                {health.status.toUpperCase()}
              </Tag>
            </Descriptions.Item>
            {Object.entries(health.checks).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                <Tag color={value === 'ok' ? 'success' : 'warning'}>{value}</Tag>
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">{t('noData')}</Typography.Text>
        )}
      </PageCard>

      <PageCard
        style={{ marginTop: 20 }}
        title={
          <PageCardTitle
            icon={
              <PageCardIcon color="#34c759" bg="rgba(52,199,89,0.12)">
                <LineChartOutlined />
              </PageCardIcon>
            }
          >
            {t('prometheusTitle')}
          </PageCardTitle>
        }
        styles={{ body: { padding: '20px 24px' } }}
      >
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          {t('prometheusLabel')}
          <a href="/api/metrics" target="_blank" rel="noreferrer">
            /api/metrics
          </a>
        </Typography.Paragraph>
        <Typography.Text type="secondary">{t('prometheusHint')}</Typography.Text>
      </PageCard>
    </PageShell>
  );
}
