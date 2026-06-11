import { Card, List, Space, Tag, Typography, theme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { PlanStep, PlanStepStatus } from '@/api/types';
import { useSemanticColors } from '@/hooks/useSemanticColors';

interface Props {
  steps: PlanStep[];
  compact?: boolean;
}

function statusIcon(status: PlanStepStatus) {
  switch (status) {
    case 'done':
      return <CheckCircleOutlined />;
    case 'in_progress':
      return <LoadingOutlined spin />;
    case 'failed':
      return <CloseCircleOutlined />;
    default:
      return <MinusCircleOutlined />;
  }
}

function statusColor(status: PlanStepStatus): string {
  switch (status) {
    case 'done':
      return 'success';
    case 'in_progress':
      return 'processing';
    case 'failed':
      return 'error';
    default:
      return 'default';
  }
}

/** 计划进度面板（FE-1 / OPT-2） */
export function PlanPanel({ steps, compact = false }: Props) {
  const { token } = theme.useToken();
  const palette = useSemanticColors();
  const { t } = useTranslation('chat');

  if (steps.length === 0) return null;

  return (
    <Card
      size="small"
      title={t('planPanelTitle')}
      style={{
        background: token.colorInfoBg,
        borderColor: token.colorInfoBorder,
        margin: compact ? 0 : '8px 16px',
      }}
    >
      <List
        size="small"
        dataSource={steps}
        renderItem={(step, index) => {
          const isActive = step.status === 'in_progress';
          return (
            <List.Item
              style={{
                padding: '6px 0',
                background: isActive ? token.colorPrimaryBg : undefined,
                borderRadius: isActive ? 6 : 0,
                paddingLeft: isActive ? 8 : 0,
                paddingRight: isActive ? 8 : 0,
              }}
            >
              <Space align="start" style={{ width: '100%' }}>
                <span
                  style={{
                    color:
                      step.status === 'done'
                        ? palette.done
                        : step.status === 'failed'
                          ? palette.failed
                          : step.status === 'in_progress'
                            ? palette.running
                            : palette.pending,
                  }}
                >
                  {statusIcon(step.status)}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Space size={6} wrap>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {index + 1}.
                    </Typography.Text>
                    <Typography.Text
                      strong={isActive}
                      style={{ fontSize: compact ? 13 : 14 }}
                    >
                      {step.goal}
                    </Typography.Text>
                    <Tag color={statusColor(step.status)} style={{ margin: 0 }}>
                      {t(`planStatus.${step.status}`)}
                    </Tag>
                  </Space>
                  {step.status === 'failed' && step.error && (
                    <Typography.Text
                      type="danger"
                      style={{ display: 'block', fontSize: 12, marginTop: 4 }}
                    >
                      {step.error}
                    </Typography.Text>
                  )}
                </div>
              </Space>
            </List.Item>
          );
        }}
      />
    </Card>
  );
}
