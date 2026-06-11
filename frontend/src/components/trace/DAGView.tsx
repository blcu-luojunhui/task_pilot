import { useEffect, useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Empty, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import i18n from '@/locales/i18n';
import type { TraceEvent } from '@/api/types';

interface StepMeta {
  step: number;
  thinkContent: string | null;
  toolCalls: string[];
  isError: boolean;
  parentTraceId?: string;
  msgToParent?: string;
  msgFromParent?: string;
}

function extractSteps(events: TraceEvent[]): StepMeta[] {
  const byStep = new Map<number, TraceEvent[]>();
  for (const evt of events) {
    if (evt.step == null) continue;
    const group = byStep.get(evt.step) || [];
    group.push(evt);
    byStep.set(evt.step, group);
  }

  const steps: StepMeta[] = [];
  for (const [step, evts] of [...byStep.entries()].sort((a, b) => a[0] - b[0])) {
    let thinkContent: string | null = null;
    const toolCalls: string[] = [];
    let isError = false;
    let parentTraceId: string | undefined;
    let msgToParent: string | undefined;
    let msgFromParent: string | undefined;

    for (const evt of evts) {
      const data = evt.data as Record<string, unknown>;

      if (evt.type === 'think_end') {
        const msg = data.assistant_message as {
          content?: string;
          tool_calls?: Array<{ function?: { name: string }; name?: string }>;
        } | undefined;
        thinkContent = (msg?.content || '').trim().slice(0, 80) || null;
        if (msg?.tool_calls) {
          for (const tc of msg.tool_calls) {
            const func = tc.function || tc;
            toolCalls.push(func.name || tc.name || '?');
          }
        }
      }

      if (evt.type === 'act_end') {
        const results = data.tool_results as Array<{ content?: string }> | undefined;
        if (results?.some((r) => (r.content ?? '').startsWith('Error:'))) {
          isError = true;
        }
      }

      if (evt.type === 'run_start') {
        const meta = data.metadata as Record<string, unknown> | undefined;
        if (meta?.parent_trace_id) {
          parentTraceId = String(meta.parent_trace_id);
        }
      }
      if (evt.type === 'step_end') {
        const payload = data as Record<string, unknown>;
        if (payload.msg_to_parent) msgToParent = String(payload.msg_to_parent);
        if (payload.msg_from_parent) msgFromParent = String(payload.msg_from_parent);
      }
    }

    steps.push({ step, thinkContent, toolCalls, isError, parentTraceId, msgToParent, msgFromParent });
  }

  return steps;
}

function buildGraph(steps: StepMeta[]): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = steps.map((s, i) => ({
    id: `step-${s.step}`,
    position: { x: i * 220, y: s.isError ? 80 : 0 },
    type: 'default',
    data: {
      label: (
        <div style={{ padding: '4px 8px', minWidth: 160 }}>
          <Handle type="target" position={Position.Top} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
            <Tag color="blue" style={{ margin: 0 }}>Step {s.step}</Tag>
            {s.isError && <Tag color="red" style={{ margin: 0 }}>{i18n.t('trace:dag.error')}</Tag>}
          </div>
          {s.thinkContent && (
            <Typography.Text
              style={{ fontSize: 11, display: 'block', marginBottom: 2 }}
              ellipsis
            >
              {s.thinkContent}
            </Typography.Text>
          )}
          {s.toolCalls.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {s.toolCalls.map((name, j) => (
                <Tag key={j} color="geekblue" style={{ fontSize: 10, margin: 0 }}>
                  {name}
                </Tag>
              ))}
            </div>
          )}
          {s.msgToParent && (
            <Typography.Text type="secondary" style={{ fontSize: 10 }}>
              → parent: {s.msgToParent}
            </Typography.Text>
          )}
          {s.msgFromParent && (
            <Typography.Text type="secondary" style={{ fontSize: 10 }}>
              ← parent: {s.msgFromParent}
            </Typography.Text>
          )}
          <Handle type="source" position={Position.Bottom} />
        </div>
      ),
    },
    style: {
      background: s.isError ? '#fff2f0' : '#fafafa',
      border: `2px solid ${s.isError ? '#ff4d4f' : '#d9d9d9'}`,
      borderRadius: 8,
      padding: 0,
    },
  }));

  const edges: Edge[] = [];
  for (let i = 1; i < nodes.length; i++) {
    edges.push({
      id: `e-step-${steps[i - 1].step}-${steps[i].step}`,
      source: `step-${steps[i - 1].step}`,
      target: `step-${steps[i].step}`,
      animated: true,
      style: { stroke: steps[i].isError ? '#ff4d4f' : '#1677ff' },
    });
  }

  return { nodes, edges };
}

export function DAGView({ events }: { events: TraceEvent[] }) {
  const { t } = useTranslation('trace');
  const steps = useMemo(() => extractSteps(events), [events]);
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => buildGraph(steps), [steps]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Re-sync when events change
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onInit = useCallback(() => {
    // ReactFlow 初始化后可加 fitView
  }, []);

  if (steps.length === 0) {
    return <Empty description={t('dag.noData')} />;
  }

  return (
    <div style={{ height: 400, width: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={onInit}
        fitView
        attributionPosition="bottom-right"
      >
        <Background />
        <Controls />
        <MiniMap
          nodeStrokeColor="#d9d9d9"
          nodeColor={(n) => {
            const bg = (n.style as Record<string, string>)?.background || '#fafafa';
            return bg === '#fff2f0' ? '#ff4d4f' : '#1677ff';
          }}
        />
      </ReactFlow>
    </div>
  );
}
