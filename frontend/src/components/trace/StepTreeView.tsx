import { Tree, Tag, Typography, Space, Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TraceEvent } from '@/api/types';
import { useSemanticColors } from '@/hooks/useSemanticColors';
import { SOURCE_COLOR } from '@/utils/colors';
import { FONT_MONO } from '@/utils/fonts';

interface ToolCallInfo {
  id: string;
  name: string;
  arguments: unknown;
}

interface ToolResultInfo {
  tool_call_id: string;
  content: string;
  is_error: boolean;
}

interface StepNode {
  step: number;
  thinkContent: string | null;
  toolCalls: ToolCallInfo[];
  toolResults: ToolResultInfo[];
  hasError: boolean;
}

function buildStepNodes(events: TraceEvent[]): StepNode[] {
  const byStep = new Map<number, TraceEvent[]>();
  for (const evt of events) {
    if (evt.step == null) continue;
    const group = byStep.get(evt.step) || [];
    group.push(evt);
    byStep.set(evt.step, group);
  }

  const nodes: StepNode[] = [];
  for (const [step, evts] of [...byStep.entries()].sort((a, b) => a[0] - b[0])) {
    let thinkContent: string | null = null;
    const toolCalls: ToolCallInfo[] = [];
    const toolResults: ToolResultInfo[] = [];

    for (const evt of evts) {
      const data = evt.data as Record<string, unknown>;

      if (evt.type === 'think_end') {
        const msg = data.assistant_message as
          | { content?: string; tool_calls?: Array<{ function?: { name: string; arguments: string }; name?: string; arguments?: unknown; id?: string }> }
          | undefined;
        thinkContent = msg?.content?.trim() || null;
        if (msg?.tool_calls) {
          for (const tc of msg.tool_calls) {
            const func = tc.function || tc;
            let args = func.arguments ?? tc.arguments;
            if (typeof args === 'string') {
              try { args = JSON.parse(args); } catch { /* keep as string */ }
            }
            toolCalls.push({
              id: tc.id || (func as Record<string, unknown>).id as string || '',
              name: func.name || tc.name || '?',
              arguments: args,
            });
          }
        }
      }

      if (evt.type === 'act_start') {
        const calls = data.tool_calls as Array<{ name: string; arguments: unknown }> | undefined;
        if (calls) {
          for (const tc of calls) {
            if (!toolCalls.some((c) => c.name === tc.name)) {
              toolCalls.push({ id: '', name: tc.name, arguments: tc.arguments });
            }
          }
        }
      }

      if (evt.type === 'act_end') {
        const results = data.tool_results as Array<{ tool_call_id?: string; content?: string }> | undefined;
        if (results) {
          for (const r of results) {
            const content = String(r.content ?? '');
            toolResults.push({
              tool_call_id: r.tool_call_id ?? '',
              content,
              is_error: content.startsWith('Error:'),
            });
          }
        }
      }
    }

    nodes.push({
      step,
      thinkContent,
      toolCalls,
      toolResults,
      hasError: toolResults.some((r) => r.is_error),
    });
  }

  return nodes;
}

export function StepTreeView({ events }: { events: TraceEvent[] }) {
  const { t } = useTranslation('trace');
  const palette = useSemanticColors();
  const nodes = buildStepNodes(events);

  if (nodes.length === 0) {
    return <Alert type="warning" showIcon message={t('stepTree.noData')} />;
  }

  const treeData = nodes.map((node) => ({
    key: `step-${node.step}`,
    title: (
      <Space size={4}>
        <Tag color="blue">Step {node.step}</Tag>
        {node.thinkContent && (
          <Typography.Text
            style={{ fontSize: 13, maxWidth: 500 }}
            ellipsis
          >
            {node.thinkContent.slice(0, 120)}
          </Typography.Text>
        )}
        {node.hasError && <Tag color="red">{t('stepTree.hasError')}</Tag>}
      </Space>
    ),
    children: node.toolCalls.length > 0
      ? node.toolCalls.map((tc, i) => {
          const result = node.toolResults.find(
            (r) => r.tool_call_id && tc.id && r.tool_call_id === tc.id
          ) || node.toolResults[i];
          const argsStr = typeof tc.arguments === 'object'
            ? JSON.stringify(tc.arguments)
            : String(tc.arguments);
          return {
            key: `step-${node.step}-tool-${i}`,
            title: (
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Space size={4}>
                  <Tag color={SOURCE_COLOR.harness ?? 'geekblue'}>{tc.name}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    <code>{argsStr.length > 100 ? argsStr.slice(0, 100) + '...' : argsStr}</code>
                  </Typography.Text>
                </Space>
                {result && (
                  <Typography.Paragraph
                    style={{
                      margin: 0,
                      padding: '4px 8px',
                      borderRadius: 4,
                      fontSize: 12,
                      background: result.is_error ? palette.stepErrorBg : palette.roleToolBg,
                      fontFamily: FONT_MONO,
                      maxHeight: 120,
                      overflow: 'auto',
                    }}
                  >
                    {result.content}
                  </Typography.Paragraph>
                )}
              </Space>
            ),
          };
        })
      : node.thinkContent
        ? [
            {
              key: `step-${node.step}-answer`,
              title: (
                <Typography.Paragraph
                  style={{ margin: 0, fontSize: 12, background: palette.stepBg, padding: 8, borderRadius: 4 }}
                >
                  {node.thinkContent}
                </Typography.Paragraph>
              ),
            },
          ]
        : undefined,
  }));

  return (
    <Tree
      treeData={treeData}
      defaultExpandAll
      showLine={{ showLeafIcon: false }}
      style={{ padding: '8px 0' }}
    />
  );
}
