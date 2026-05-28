import { useEffect, useState } from 'react';
import { Alert, Card, Descriptions, Space, Spin, Tag, Typography } from 'antd';
import { getHealth, type HealthData } from '@/api/system';

export function SystemPage() {
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
        message="System — 系统监控"
        description="只读快照：健康检查、Prometheus 指标。Phase 3 接入指标可视化。"
      />
      <Card title="健康检查 (/api/health)" variant="borderless">
        {loading ? (
          <Spin />
        ) : health ? (
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="总体">
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
          <Typography.Text type="secondary">无数据</Typography.Text>
        )}
      </Card>

      <Card title="Prometheus Metrics" variant="borderless">
        <Typography.Paragraph>
          原始指标接口：
          <a href="/api/metrics" target="_blank" rel="noreferrer">
            /api/metrics
          </a>
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          建议接入 Grafana 后做完整可视化；前端可后续引入 recharts 渲染关键指标。
        </Typography.Text>
      </Card>
    </Space>
  );
}
