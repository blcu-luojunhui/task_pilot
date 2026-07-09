import dagre from '@dagrejs/dagre';
import type { CSSProperties } from 'react';
import type { TraceGraph, TraceGraphEdge } from './traceGraph';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 100;

/** dagre 自动布局坐标，保留用户已拖动位置（FE-2） */
export function computeDagrePositions(
  graph: TraceGraph,
  existingPositions: Record<string, { x: number; y: number }>,
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70, marginx: 20, marginy: 20 });

  for (const node of graph.nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of graph.edges) {
    g.setEdge(edge.source, edge.target);
  }

  if (graph.nodes.length > 0) {
    dagre.layout(g);
  }

  const positions: Record<string, { x: number; y: number }> = {};
  for (const node of graph.nodes) {
    if (existingPositions[node.id]) {
      positions[node.id] = existingPositions[node.id];
      continue;
    }
    const layoutPos = g.node(node.id);
    positions[node.id] = {
      x: (layoutPos?.x ?? 0) - NODE_WIDTH / 2,
      y: (layoutPos?.y ?? 0) - NODE_HEIGHT / 2,
    };
  }
  return positions;
}

export function buildFlowEdges(
  edges: TraceGraphEdge[],
  palette: { edge: string; edgeError: string; done: string; failed: string },
): Array<{
  id: string;
  source: string;
  target: string;
  animated: boolean;
  style: CSSProperties;
  label?: string;
  labelStyle?: CSSProperties;
}> {
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: e.kind !== 'handoff',
    style: {
      stroke:
        e.kind === 'handoff'
          ? palette.failed
          : e.kind === 'dependency'
            ? palette.done
            : palette.edge,
      strokeWidth: e.kind === 'handoff' ? 2.5 : 1.5,
      strokeDasharray: e.kind === 'handoff' ? '6 4' : undefined,
    },
    label: e.kind === 'handoff' ? 'handoff' : undefined,
    labelStyle: { fontSize: 10 },
  }));
}

export const DAG_NODE_SIZE = { width: NODE_WIDTH, height: NODE_HEIGHT };
