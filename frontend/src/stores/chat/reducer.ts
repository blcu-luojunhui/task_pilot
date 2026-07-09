import type {
  ChatMessage,
  TokenUsage,
  TraceEvent,
} from '@/api/types';

/** SSE 驱动的实时 UI 状态（纯文本对话） */
export interface ChatLiveState {
  liveStreamingText: string;
  sessionTokenUsage: TokenUsage;
  cacheTokensSaved: number;
}

const emptyTokenUsage = (): TokenUsage => ({ prompt: 0, completion: 0, total: 0 });

export const initialChatLiveState: ChatLiveState = {
  liveStreamingText: '',
  sessionTokenUsage: emptyTokenUsage(),
  cacheTokensSaved: 0,
};

export interface ChatReduceContext {
  activeConversationId: string | null;
}

/** reducer 副作用：由 store 层执行（刷新消息、更新 inFlight 等） */
export interface ChatReduceEffects {
  refreshMessages?: boolean;
  setInFlight?: boolean;
  setActiveTraceId?: string | null;
  appendMessages?: ChatMessage[];
}

export interface ChatReduceResult {
  live: ChatLiveState;
  effects: ChatReduceEffects;
}

/**
 * 纯函数：将 SSE 事件归约为实时 UI 状态。
 * 纯文本对话模式下只需处理 token_delta 和 turn_end。
 */
export function reduceChatEvent(
  live: ChatLiveState,
  event: TraceEvent,
  _ctx: ChatReduceContext,
): ChatReduceResult {
  const data = event.data ?? {};
  const effects: ChatReduceEffects = {};
  let next: ChatLiveState = live;

  switch (event.type) {
    case 'chat.token_delta': {
      const delta = (data.delta as string) ?? '';
      if (delta) {
        next = { ...live, liveStreamingText: live.liveStreamingText + delta };
      } else {
        const accumulated = (data.accumulated as string) ?? '';
        if (accumulated) {
          next = { ...live, liveStreamingText: accumulated };
        }
      }
      break;
    }

    case 'chat.turn_end': {
      const usage = data.token_usage as TokenUsage | undefined;
      next = {
        ...live,
        sessionTokenUsage: usage
          ? {
              prompt: live.sessionTokenUsage.prompt + (usage.prompt ?? 0),
              completion: live.sessionTokenUsage.completion + (usage.completion ?? 0),
              total: live.sessionTokenUsage.total + (usage.total ?? 0),
            }
          : live.sessionTokenUsage,
      };
      break;
    }

    default:
      break;
  }

  return { live: next, effects };
}
