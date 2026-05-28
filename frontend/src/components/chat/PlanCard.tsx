import { Card, Steps, Tag, Typography, theme } from 'antd';
import { OrderedListOutlined } from '@ant-design/icons';
import { useMemo } from 'react';
import type { ChatToolCall } from '@/api/types';

interface Props {
  toolCall: ChatToolCall;
}

interface ParsedPlan {
  title?: string;
  rationale?: string;
  steps: Array<{
    title: string;
    description?: string;
    task_name?: string | null;
  }>;
}

function parsePlanArgs(tc: ChatToolCall): ParsedPlan | null {
  try {
    const rawArgs = tc.function?.arguments ?? tc.arguments;
    if (!rawArgs) return null;
    const parsed = typeof rawArgs === 'string' ? JSON.parse(rawArgs) : rawArgs;
    if (!parsed || typeof parsed !== 'object') return null;
    if (parsed.type !== 'plan' && !parsed.steps) return null;
    return parsed as ParsedPlan;
  } catch {
    return null;
  }
}

export function PlanCard({ toolCall }: Props) {
  const { token } = theme.useToken();
  const plan = useMemo(() => parsePlanArgs(toolCall), [toolCall]);
  if (!plan) return null;

  return (
    <Card
      size="small"
      style={{ background: token.colorPrimaryBg, borderColor: token.colorPrimaryBorder }}
      title={
        <Tag icon={<OrderedListOutlined />} color="blue">
          plan
        </Tag>
      }
    >
      {plan.title && (
        <Typography.Title level={5} style={{ margin: 0 }}>
          {plan.title}
        </Typography.Title>
      )}
      {plan.rationale && (
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
          {plan.rationale}
        </Typography.Paragraph>
      )}
      {plan.steps && plan.steps.length > 0 && (
        <Steps
          direction="vertical"
          size="small"
          current={-1}
          items={plan.steps.map((s) => ({
            title: s.title,
            description: s.task_name ? (
              <span>
                task: <code>{s.task_name}</code>
                {s.description && ` — ${s.description}`}
              </span>
            ) : (
              s.description
            ),
          }))}
        />
      )}
    </Card>
  );
}
