import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '@/api/types';
import { buildMessageParts } from './messageParts';

function baseMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 1,
    conversation_id: 'c1',
    role: 'user',
    content: null,
    tool_calls: null,
    tool_call_id: null,
    trace_id: null,
    token_usage: null,
    status: 0,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('buildMessageParts', () => {
  it('returns text part for user message', () => {
    const message = baseMessage({ role: 'user', content: 'Hello' });
    expect(buildMessageParts(message)).toEqual([{ kind: 'text', text: 'Hello' }]);
  });

  it('parses plan_tasks tool call into plan part', () => {
    const message = baseMessage({
      role: 'assistant',
      content: '',
      tool_calls: [
        {
          id: 'tc1',
          function: {
            name: 'plan_tasks',
            arguments: JSON.stringify({ tasks: [{ goal: 'Step A', status: 'pending' }] }),
          },
        },
      ],
    });
    const parts = buildMessageParts(message);
    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({
      kind: 'plan',
      steps: [{ id: '0', goal: 'Step A', status: 'pending' }],
    });
  });

  it('parses spawn_subagent into subagent part', () => {
    const message = baseMessage({
      role: 'assistant',
      content: '',
      tool_calls: [
        {
          id: 'tc2',
          function: {
            name: 'spawn_subagent',
            arguments: JSON.stringify({
              child_trace_id: 'Agent-123',
              goal: 'Research',
              summary: 'Done',
            }),
          },
        },
      ],
    });
    const parts = buildMessageParts(message);
    expect(parts[0]).toMatchObject({
      kind: 'subagent',
      traceId: 'Agent-123',
      goal: 'Research',
      summary: 'Done',
    });
  });

  it('falls back to tool part for generic tool calls', () => {
    const message = baseMessage({
      role: 'assistant',
      content: 'Calling tool',
      tool_calls: [
        {
          id: 'tc3',
          function: { name: 'search', arguments: '{"q":"test"}' },
        },
      ],
    });
    const parts = buildMessageParts(message);
    expect(parts[0]).toMatchObject({ kind: 'text', text: 'Calling tool' });
    expect(parts[1]).toMatchObject({ kind: 'tool', toolName: 'search', status: 'completed' });
  });
});
