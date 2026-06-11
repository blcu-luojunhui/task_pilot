import { useEffect, useState } from 'react';
import { Button, Drawer, Empty, Space, Spin, Table, Tag, Typography } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { SkillCallRecord, SkillInfo } from '@/api/types';
import { getSkillCalls } from '@/api/skills';

interface Props {
  skill: SkillInfo | null;
  open: boolean;
  onClose: () => void;
}

export function SkillCallHistoryDrawer({ skill, open, onClose }: Props) {
  const { t } = useTranslation('skills');
  const [loading, setLoading] = useState(false);
  const [calls, setCalls] = useState<SkillCallRecord[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    if (!skill || !open) return;
    setLoading(true);
    getSkillCalls(skill.name, 50)
      .then((data) => setCalls(data.calls))
      .finally(() => setLoading(false));
  }, [skill, open]);

  const columns = [
    {
      title: 'Trace',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 180,
      render: (traceId: string) => (
        <Button
          type="link"
          size="small"
          icon={<LinkOutlined />}
          onClick={() => {
            navigate(`/tasks/${encodeURIComponent(traceId)}`);
            onClose();
          }}
          style={{ padding: 0, fontSize: 12 }}
        >
          <code style={{ fontSize: 11 }}>{traceId.slice(-16)}</code>
        </Button>
      ),
    },
    {
      title: 'Step',
      dataIndex: 'step',
      key: 'step',
      width: 60,
      render: (step: number | null) =>
        step !== null ? <Tag color="blue">{step}</Tag> : '-',
    },
    {
      title: t('paramsLabel'),
      dataIndex: 'arguments',
      key: 'arguments',
      ellipsis: true,
      render: (args: unknown) => (
        <Typography.Text style={{ fontSize: 11, fontFamily: 'ui-monospace, monospace' }}>
          <code>{JSON.stringify(args)}</code>
        </Typography.Text>
      ),
    },
    {
      title: t('timeLabel'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (ts: string) => (
        <Typography.Text style={{ fontSize: 11 }}>{ts}</Typography.Text>
      ),
    },
  ];

  return (
    <Drawer
      title={
        skill && (
          <Space>
            <Typography.Text strong>{skill.name}</Typography.Text>
            <Tag>{skill.risk_level}</Tag>
          </Space>
        )
      }
      open={open}
      onClose={onClose}
      width={640}
    >
      {loading ? (
        <Spin />
      ) : calls.length === 0 ? (
        <Empty description={t('noCallsRecord', { name: skill?.name ?? t('unknown') })} />
      ) : (
        <Table
          dataSource={calls}
          rowKey={(r: SkillCallRecord) => `${r.trace_id}-${r.sequence}`}
          columns={columns}
          size="small"
          pagination={{ pageSize: 20, size: 'small' }}
        />
      )}
    </Drawer>
  );
}
