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

  it('accumulates token usage on turn_end', () => {
    const result = reduceChatEvent(
      initialChatLiveState,
      evt('chat.turn_end', {
        token_usage: { prompt: 100, completion: 50, total: 150 },
      }),
      { activeConversationId: 'c1' },
    );
    expect(result.live.sessionTokenUsage.total).toBe(150);
  });

  it('accumulates token usage across multiple turns', () => {
    const r1 = reduceChatEvent(
      initialChatLiveState,
      evt('chat.turn_end', {
        token_usage: { prompt: 80, completion: 40, total: 120 },
      }),
      { activeConversationId: 'c1' },
    );

    const r2 = reduceChatEvent(
      r1.live,
      evt('chat.turn_end', {
        token_usage: { prompt: 60, completion: 30, total: 90 },
      }),
      { activeConversationId: 'c1' },
    );

    expect(r2.live.sessionTokenUsage.prompt).toBe(140);
    expect(r2.live.sessionTokenUsage.completion).toBe(70);
    expect(r2.live.sessionTokenUsage.total).toBe(210);
  });

  it('ignores unknown event types', () => {
    const result = reduceChatEvent(
      initialChatLiveState,
      evt('chat.unknown_event', { data: 'ignored' }),
      { activeConversationId: 'c1' },
    );
    expect(result.live).toEqual(initialChatLiveState);
  });
});
