import { useEffect, useState } from 'react';
import { Button, Card, Col, Row, Space, Spin, Statistic, Tag, Typography } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';
import { listSkills } from '@/api/skills';
import type { SkillInfo } from '@/api/types';
import { SkillCallHistoryDrawer } from '@/components/skill/SkillCallHistoryDrawer';
import { RISK_COLOR } from '@/utils/colors';

export function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerSkill, setDrawerSkill] = useState<SkillInfo | null>(null);

  useEffect(() => {
    setLoading(true);
    listSkills()
      .then(setSkills)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin />;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        Skills 注册表
      </Typography.Title>
      <Typography.Text type="secondary">
        Agent 通过 `@skill` 装饰器注册的工具能力。按 category 分类，按 risk_level 标色。
      </Typography.Text>
      <Row gutter={[16, 16]}>
        {skills.map((s) => (
          <Col key={s.skill_id} xs={24} md={12} xl={8}>
            <Card
              size="small"
              title={
                <Space>
                  <Typography.Text strong>{s.name}</Typography.Text>
                  <Tag color={RISK_COLOR[s.risk_level]}>{s.risk_level}</Tag>
                </Space>
              }
              extra={<Tag>{s.category}</Tag>}
            >
              <Typography.Paragraph style={{ minHeight: 44 }}>{s.description}</Typography.Paragraph>
              <Space split={<span style={{ color: '#d9d9d9' }}>·</span>}>
                <Statistic
                  title="参数数"
                  value={Object.keys(s.parameters).length}
                  valueStyle={{ fontSize: 16 }}
                />
                <Statistic
                  title="近 24h 调用"
                  value={s.call_count_24h ?? 0}
                  valueStyle={{ fontSize: 16 }}
                />
              </Space>
              {Object.keys(s.parameters).length > 0 && (
                <details style={{ marginTop: 12 }}>
                  <summary style={{ cursor: 'pointer', color: '#1677ff' }}>查看 schema</summary>
                  <pre style={{ fontSize: 12, marginTop: 8 }}>
                    {JSON.stringify(s.parameters, null, 2)}
                  </pre>
                </details>
              )}
              <Button
                type="link"
                size="small"
                icon={<HistoryOutlined />}
                onClick={() => setDrawerSkill(s)}
                style={{ padding: 0, marginTop: 8 }}
              >
                Recent Calls
              </Button>
            </Card>
          </Col>
        ))}
      </Row>
      <SkillCallHistoryDrawer
        skill={drawerSkill}
        open={drawerSkill !== null}
        onClose={() => setDrawerSkill(null)}
      />
    </Space>
  );
}
