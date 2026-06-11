import { useEffect, useState } from 'react';
import { Alert, Card, Descriptions, Space, Spin, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { getHealth, type HealthData } from '@/api/system';

export function SystemPage() {
  const { t } = useTranslation('system');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getHealth()
      .then(setHealth)
      .finally(() => setLoading(false));
  }, []);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={t('title')}
        description={t('description')}
      />
      <Card title={t('healthCheck')} variant="borderless">
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
      </Card>

      <Card title={t('prometheusTitle')} variant="borderless">
        <Typography.Paragraph>
          {t('prometheusLabel')}
          <a href="/api/metrics" target="_blank" rel="noreferrer">
            /api/metrics
          </a>
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          {t('prometheusHint')}
        </Typography.Text>
      </Card>
    </Space>
  );
}
