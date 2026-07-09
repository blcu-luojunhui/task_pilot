import { useMemo, useState } from 'react';
import { Collapse, Empty, Select, Space, Tag, Typography } from 'antd';
import { DiffOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TraceEvent } from '@/api/types';
import { useSemanticColors } from '@/hooks/useSemanticColors';
import { FONT_MONO } from '@/utils/fonts';

interface PromptSnapshot {
  step: number;
  messages: Array<{ role: string; content: string; tool_call_id?: string }>;
  toolsSpec: unknown;
  totalChars: number;
  estimatedTokens: number;
}

function extractPrompts(events: TraceEvent[]): PromptSnapshot[] {
  return events
    .filter((e) => e.type === 'prompt_assembled')
    .map((e) => {
      const data = e.data as {
        messages?: Array<{ role: string; content: string; tool_call_id?: string }>;
        tools_spec?: unknown;
      };
      const messages = data.messages || [];
      const totalChars = messages.reduce(
        (s, m) => s + (typeof m.content === 'string' ? m.content.length : 0),
        0
      );
      return {
        step: e.step ?? 0,
        messages,
        toolsSpec: data.tools_spec,
        totalChars,
        estimatedTokens: Math.ceil(totalChars / 4),
      };
    });
}

export function PromptInspector({ events }: { events: TraceEvent[] }) {
  const { t } = useTranslation('trace');
  const palette = useSemanticColors();
  const roleBg: Record<string, string> = {
    system: palette.roleSystemBg,
    user: palette.roleUserBg,
    assistant: palette.roleAssistantBg,
    tool: palette.roleToolBg,
  };
  const prompts = useMemo(() => extractPrompts(events), [events]);
  const [compareStep, setCompareStep] = useState<number | null>(null);

  if (prompts.length === 0) {
    return (
      <Empty description={t('prompt.noData')} />
    );
  }

  const latest = prompts[prompts.length - 1];
  const compareTo = compareStep !== null
    ? prompts.find((p) => p.step === compareStep)
    : (prompts.length > 1 ? prompts[prompts.length - 2] : null);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', padding: '8px 0' }}>
      <Space size={8} wrap>
        <Typography.Text strong>{t('prompt.snapshots')}</Typography.Text>
        <Tag color="blue">{prompts.length}</Tag>
        <Select
          size="small"
          placeholder={t('prompt.compareStep')}
          allowClear
          style={{ width: 120 }}
          options={prompts
            .filter((p) => p.step !== latest.step)
            .map((p) => ({ value: p.step, label: `Step ${p.step}` }))}
          value={compareStep}
          onChange={(v) => setCompareStep(v ?? null)}
        />
      </Space>

      {/* 统计 */}
      <Space size={24} wrap>
        <Tag icon={<DiffOutlined />}>
          {latest.messages.length} messages
        </Tag>
        <Tag color="blue">{latest.totalChars.toLocaleString()} chars</Tag>
        <Tag color="cyan">~{latest.estimatedTokens.toLocaleString()} tokens</Tag>
        {latest.toolsSpec ? (
          <Tag color="purple">
            {Array.isArray(latest.toolsSpec)
              ? `${latest.toolsSpec.length} tools`
              : 'tools spec'}
          </Tag>
        ) : null}
      </Space>

      {/* Side-by-side diff 模式 */}
      {compareTo && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Step {compareTo.step} ({compareTo.messages.length} msgs, ~{compareTo.estimatedTokens} tok)
            </Typography.Text>
          </div>
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Step {latest.step} ({latest.messages.length} msgs, ~{latest.estimatedTokens} tok)
              {latest.totalChars > compareTo.totalChars && (
                <Tag color="orange" style={{ marginLeft: 4 }}>
                  +{((latest.totalChars - compareTo.totalChars) / 1024).toFixed(1)} KB
                </Tag>
              )}
            </Typography.Text>
          </div>
        </div>
      )}

      {/* 消息列表 */}
      <Collapse
        accordion
        size="small"
        items={latest.messages.map((msg, i) => ({
          key: String(i),
          label: (
            <Space size={4}>
              <Tag color="default" style={{ fontSize: 10 }}>
                #{i + 1} {msg.role}
              </Tag>
              <Typography.Text
                type="secondary"
                style={{ fontSize: 11, maxWidth: 400 }}
                ellipsis
              >
                {typeof msg.content === 'string'
                  ? msg.content.slice(0, 100).replace(/\n/g, ' ')
                  : ''}
              </Typography.Text>
            </Space>
          ),
          children: (
            <div
              style={{
                background: roleBg[msg.role] || palette.stepBg,
                padding: 8,
                borderRadius: 4,
                maxHeight: 400,
                overflow: 'auto',
                fontSize: 12,
                fontFamily: FONT_MONO,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {msg.content || <Typography.Text type="secondary">(empty)</Typography.Text>}
            </div>
          ),
        }))}
      />
    </Space>
  );
}
