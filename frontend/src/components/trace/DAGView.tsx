import { useCallback, useEffect, useMemo, useRef } from 'react';
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
  type NodeChange,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Empty, Tag, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TraceEvent } from '@/api/types';
import { useSemanticColors } from '@/hooks/useSemanticColors';
import { parseTraceGraph, type TraceGraphNode } from '@/utils/traceGraph';
import { buildFlowEdges, computeDagrePositions, DAG_NODE_SIZE } from '@/utils/dagLayout';

function TraceStepNode({ data }: NodeProps) {
  const node = data.graphNode as TraceGraphNode;
  if (!node) return null;
  return <StepNodeLabel node={node} />;
}

function StepNodeLabel({ node }: { node: TraceGraphNode }) {
  const { t } = useTranslation('trace');

  const statusColor =
    node.status === 'failed' || node.isError
      ? 'error'
      : node.status === 'running'
        ? 'processing'
        : node.status === 'done'
          ? 'success'
          : 'default';

  return (
    <div style={{ padding: '4px 8px', minWidth: 160 }}>
      <Handle type="target" position={Position.Top} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4, flexWrap: 'wrap' }}>
        <Tag color="blue" style={{ margin: 0 }}>
          Step {node.step}
        </Tag>
        <Tag color={statusColor} style={{ margin: 0 }}>
          {node.status}
        </Tag>
        {(node.status === 'failed' || node.isError) && (
          <Tag color="red" style={{ margin: 0 }}>
            {t('dag.error')}
          </Tag>
        )}
      </div>
      {node.thinkContent && (
        <Typography.Text style={{ fontSize: 11, display: 'block', marginBottom: 2 }} ellipsis>
          {node.thinkContent}
        </Typography.Text>
      )}
      {node.toolCalls.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
          {node.toolCalls.map((name, j) => (
            <Tag key={j} color="geekblue" style={{ fontSize: 10, margin: 0 }}>
              {name}
            </Tag>
          ))}
        </div>
      )}
      {node.subagentTraceId && (
        <Typography.Text type="secondary" style={{ fontSize: 10, display: 'block' }}>
          sub: {node.subagentTraceId.slice(0, 16)}…
        </Typography.Text>
      )}
      {node.msgToParent && (
        <Typography.Text type="secondary" style={{ fontSize: 10 }}>
          → parent: {node.msgToParent}
        </Typography.Text>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = {
  traceStep: TraceStepNode,
};

function graphToFlow(
  graph: ReturnType<typeof parseTraceGraph>,
  positions: Record<string, { x: number; y: number }>,
  palette: ReturnType<typeof useSemanticColors>,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = graph.nodes.map((n) => {
    const pos = positions[n.id] ?? { x: 0, y: 0 };
    const borderColor =
      n.status === 'failed' || n.isError
        ? palette.stepErrorBorder
        : n.status === 'running'
          ? palette.running
          : palette.stepBorder;
    const bg = n.status === 'failed' || n.isError ? palette.stepErrorBg : palette.stepBg;

    return {
      id: n.id,
      type: 'traceStep',
      position: pos,
      data: { graphNode: n },
      style: {
        background: bg,
        border: `2px solid ${borderColor}`,
        borderRadius: 8,
        padding: 0,
        width: DAG_NODE_SIZE.width,
      },
    };
  });

  const edges = buildFlowEdges(graph.edges, palette) as Edge[];
  return { nodes, edges };
}

export function DAGView({
  events,
  selectedStep,
  onSelectStep,
}: {
  events: TraceEvent[];
  selectedStep?: number | null;
  onSelectStep?: (step: number | null) => void;
}) {
  const { t } = useTranslation('trace');
  const { token } = theme.useToken();
  const palette = useSemanticColors();
  const savedPositions = useRef<Record<string, { x: number; y: number }>>({});

  const graph = useMemo(() => parseTraceGraph(events), [events]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    const positions = computeDagrePositions(graph, savedPositions.current);
    const { nodes: nextNodes, edges: nextEdges } = graphToFlow(graph, positions, palette);

    setNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      return nextNodes.map((n) => ({
        ...n,
        position: prevPos.get(n.id) ?? n.position,
      }));
    });
    setEdges(nextEdges);
  }, [graph, palette, setNodes, setEdges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(changes);
      for (const ch of changes) {
        if (ch.type === 'position' && ch.position && !ch.dragging) {
          savedPositions.current[ch.id] = ch.position;
        }
      }
    },
    [onNodesChange],
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const gn = (node.data as { graphNode?: TraceGraphNode }).graphNode;
      onSelectStep?.(gn?.step ?? null);
    },
    [onSelectStep],
  );

  if (graph.nodes.length === 0) {
    return <Empty description={t('dag.noData')} />;
  }

  return (
    <div style={{ height: 420, width: '100%' }}>
      <ReactFlow
        nodes={nodes.map((n) => ({
          ...n,
          selected:
            (n.data as { graphNode?: TraceGraphNode }).graphNode?.step === selectedStep,
        }))}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        attributionPosition="bottom-right"
      >
        <Background color={token.colorBorderSecondary} />
        <Controls />
        <MiniMap
          nodeStrokeColor={token.colorBorder}
          nodeColor={(n) => {
            const gn = (n.data as { graphNode?: TraceGraphNode }).graphNode;
            if (gn?.isError || gn?.status === 'failed') return palette.failed;
            if (gn?.status === 'running') return palette.running;
            return palette.done;
          }}
        />
      </ReactFlow>
    </div>
  );
}
