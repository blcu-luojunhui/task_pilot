import { describe, expect, it } from 'vitest';
import type { TraceEvent } from '@/api/types';
import { initialChatLiveState, reduceChatEvent } from './reducer';

function evt(type: string, data: Record<string, unknown> = {}): TraceEvent {
  return {
    sequence: 1,
    type,
    trace_id: 'Chat-test',
    step: null,
    source: 'chat',
    timestamp: new Date().toISOString(),
    data,
  };
}

describe('reduceChatEvent', () => {
  it('accumulates token deltas', () => {
    const r1 = reduceChatEvent(initialChatLiveState, evt('chat.token_delta', { delta: 'Hi' }), {
      activeConversationId: 'c1',
    });
    expect(r1.live.liveStreamingText).toBe('Hi');

    const r2 = reduceChatEvent(r1.live, evt('chat.token_delta', { delta: ' there' }), {
      activeConversationId: 'c1',
    });
    expect(r2.live.liveStreamingText).toBe('Hi there');
  });

  it('tracks tool call lifecycle', () => {
    const start = reduceChatEvent(
      initialChatLiveState,
      evt('chat.tool_call_start', {
        call_id: 'c1',
        tool_name: 'list_recent_tasks',
        arguments: { limit: 5 },
      }),
      { activeConversationId: 'c1' },
    );
    expect(start.live.liveToolCalls).toHaveLength(1);
    expect(start.live.liveToolCalls[0].status).toBe('running');

    const end = reduceChatEvent(
      start.live,
      evt('chat.tool_call_end', { call_id: 'c1', ok: true, result: { items: [] } }),
      { activeConversationId: 'c1' },
    );
    expect(end.live.liveToolCalls[0].status).toBe('completed');
  });

  it('handles plan_updated and strategy', () => {
    const plan = reduceChatEvent(
      initialChatLiveState,
      evt('chat.plan_updated', {
        steps: [{ goal: 'step 1', status: 'in_progress' }],
      }),
      { activeConversationId: 'c1' },
    );
    expect(plan.live.plan).toHaveLength(1);

    const strategy = reduceChatEvent(
      plan.live,
      evt('chat.strategy', { mode: 'plan_execute' }),
      { activeConversationId: 'c1' },
    );
    expect(strategy.live.strategy).toBe('plan_execute');
  });

  it('accumulates token usage on turn_end', () => {
    const result = reduceChatEvent(
      initialChatLiveState,
      evt('chat.turn_end', {
        token_usage: { prompt: 100, completion: 50, total: 150 },
      }),
      { activeConversationId: 'c1' },
    );
    expect(result.live.sessionTokenUsage.total).toBe(150);
    expect(result.live.lifecycle).toBe('idle');
  });

  it('handles artifact and cache_hit', () => {
    const artifact = reduceChatEvent(
      initialChatLiveState,
      evt('chat.artifact_created', {
        artifact: { id: 'art-1', summary: 'large result' },
      }),
      { activeConversationId: 'c1' },
    );
    expect(artifact.live.artifacts).toHaveLength(1);

    const cache = reduceChatEvent(
      artifact.live,
      evt('chat.cache_hit', { tokens_saved: 200 }),
      { activeConversationId: 'c1' },
    );
    expect(cache.live.cacheTokensSaved).toBe(200);
  });

  it('pauses on turn_paused with refresh side effect', () => {
    const result = reduceChatEvent(initialChatLiveState, evt('chat.turn_paused'), {
      activeConversationId: 'c1',
    });
    expect(result.effects.setInFlight).toBe(false);
    expect(result.effects.refreshMessages).toBe(true);
  });
});
