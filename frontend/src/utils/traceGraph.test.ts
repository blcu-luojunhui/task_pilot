import { describe, expect, it } from 'vitest';
import { buildDagTraceEvents } from '@/mocks/fixtures/events';
import { parseTraceGraph } from './traceGraph';

describe('parseTraceGraph', () => {
  it('parses diamond dependency edges from step deps', () => {
    const events = buildDagTraceEvents('Agent-test-dag');
    const graph = parseTraceGraph(events);

    expect(graph.nodes.length).toBeGreaterThanOrEqual(4);

    const depEdges = graph.edges.filter((e) => e.kind === 'dependency');
    expect(depEdges.some((e) => e.source === 'step-1' && e.target === 'step-2')).toBe(true);
    expect(depEdges.some((e) => e.source === 'step-1' && e.target === 'step-3')).toBe(true);
    expect(depEdges.some((e) => e.source === 'step-2' && e.target === 'step-4')).toBe(true);
    expect(depEdges.some((e) => e.source === 'step-3' && e.target === 'step-4')).toBe(true);
  });

  it('detects handoff edges', () => {
    const events = buildDagTraceEvents('Agent-test-dag');
    const graph = parseTraceGraph(events);
    expect(graph.edges.some((e) => e.kind === 'handoff')).toBe(true);
  });

  it('attaches subagent trace id to step node', () => {
    const events = buildDagTraceEvents('Agent-test-dag');
    const graph = parseTraceGraph(events);
    const step3 = graph.nodes.find((n) => n.step === 3);
    expect(step3?.subagentTraceId).toContain('-sub-1');
  });
});
