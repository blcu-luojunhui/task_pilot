import type { TraceEvent } from '@/api/types';

export type GraphNodeStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export type TraceEdgeKind = 'sequential' | 'dependency' | 'handoff';

export interface TraceGraphNode {
  id: string;
  step: number;
  thinkContent: string | null;
  toolCalls: string[];
  status: GraphNodeStatus;
  isError: boolean;
  parentTraceId?: string;
  subagentTraceId?: string;
  groupId?: string;
  msgToParent?: string;
  msgFromParent?: string;
}

export interface TraceGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: TraceEdgeKind;
}

export interface TraceGraph {
  nodes: TraceGraphNode[];
  edges: TraceGraphEdge[];
}

function stepId(step: number): string {
  return `step-${step}`;
}

/** 从 trace 事件解析真实依赖图（FE-2 / OPT-7/9/10） */
export function parseTraceGraph(events: TraceEvent[]): TraceGraph {
  const byStep = new Map<number, TraceEvent[]>();
  const stepDeps = new Map<number, number[]>();
  const handoffs: Array<{ from: number; to: number; target?: string }> = [];
  const subagents = new Map<number, string>();
  let maxStep = 0;

  for (const evt of events) {
    if (evt.step != null) {
      maxStep = Math.max(maxStep, evt.step);
      const group = byStep.get(evt.step) || [];
      group.push(evt);
      byStep.set(evt.step, group);
    }

    const data = evt.data as Record<string, unknown>;

    if (evt.type === 'step_start' && evt.step != null) {
      const deps = data.deps as number[] | undefined;
      if (deps?.length) {
        stepDeps.set(evt.step, deps);
      }
    }

    if (evt.type === 'plan_decomposed' || evt.type === 'sub_tasks_created') {
      const tasks = (data.sub_tasks as Array<{ id?: string; goal?: string; deps?: number[] }>) ?? [];
      tasks.forEach((t, i) => {
        const stepNum = i + 1;
        if (t.deps?.length) {
          stepDeps.set(stepNum, t.deps);
        }
      });
    }

    if (evt.type === 'handoff' || evt.type === 'agent.handoff') {
      const from = (data.from_step as number) ?? evt.step ?? 0;
      const to = (data.to_step as number) ?? from + 1;
      handoffs.push({ from, to, target: data.target_agent_id as string | undefined });
    }

    if (evt.type === 'subagent_spawned' || evt.type === 'spawn_subagent') {
      const step = evt.step ?? 0;
      const childTrace = (data.child_trace_id as string) ?? (data.trace_id as string);
      if (childTrace) {
        subagents.set(step, childTrace);
      }
    }
  }

  const nodes: TraceGraphNode[] = [];
  const steps = [...byStep.keys()].sort((a, b) => a - b);

  for (const step of steps) {
    const evts = byStep.get(step) ?? [];
    let thinkContent: string | null = null;
    const toolCalls: string[] = [];
    let isError = false;
    let status: GraphNodeStatus = 'done';
    let parentTraceId: string | undefined;
    let msgToParent: string | undefined;
    let msgFromParent: string | undefined;

    for (const evt of evts) {
      const data = evt.data as Record<string, unknown>;

      if (evt.type === 'step_start') {
        status = 'running';
      }
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
          status = 'failed';
        }
      }
      if (evt.type === 'run_start') {
        const meta = data.metadata as Record<string, unknown> | undefined;
        if (meta?.parent_trace_id) {
          parentTraceId = String(meta.parent_trace_id);
        }
      }
      if (evt.type === 'step_end') {
        status = isError ? 'failed' : 'done';
        if (data.msg_to_parent) msgToParent = String(data.msg_to_parent);
        if (data.msg_from_parent) msgFromParent = String(data.msg_from_parent);
      }
      if (evt.type === 'run_error') {
        isError = true;
        status = 'failed';
      }
    }

    const subagentTraceId = subagents.get(step);
    nodes.push({
      id: stepId(step),
      step,
      thinkContent,
      toolCalls,
      status,
      isError,
      parentTraceId,
      subagentTraceId,
      groupId: parentTraceId ? `group-${parentTraceId}` : undefined,
      msgToParent,
      msgFromParent,
    });
  }

  const edges: TraceGraphEdge[] = [];
  const edgeKeys = new Set<string>();

  const addEdge = (source: string, target: string, kind: TraceEdgeKind) => {
    const key = `${source}->${target}:${kind}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    edges.push({ id: key, source, target, kind });
  };

  // 显式 deps 边（OPT-7）
  for (const [step, deps] of stepDeps.entries()) {
    for (const dep of deps) {
      addEdge(stepId(dep), stepId(step), 'dependency');
    }
  }

  // handoff 边（OPT-10）
  for (const h of handoffs) {
    if (h.from > 0 && h.to > 0) {
      addEdge(stepId(h.from), stepId(h.to), 'handoff');
    }
  }

  // 无显式 deps 时回退为顺序边
  if (stepDeps.size === 0 && handoffs.length === 0 && steps.length > 1) {
    for (let i = 1; i < steps.length; i++) {
      addEdge(stepId(steps[i - 1]), stepId(steps[i]), 'sequential');
    }
  }

  return { nodes, edges };
}
