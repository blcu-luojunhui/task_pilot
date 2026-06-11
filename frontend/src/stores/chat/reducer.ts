import type {
  AgentLifecycleState,
  ArtifactRef,
  ChatMessage,
  ChatMessageStatus,
  ChatToolCall,
  PlanStep,
  TokenUsage,
  ToolCall,
  TraceEvent,
} from '@/api/types';

export interface ToolCallStatus {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'completed' | 'failed';
  result?: unknown;
}

export interface PendingPlan {
  messageId: number;
  toolCalls: ToolCall[];
  conversationId: string;
}

/** SSE 驱动的实时 UI 状态（FE-6 事件溯源 reducer） */
export interface ChatLiveState {
  liveStreamingText: string;
  liveToolCalls: ToolCallStatus[];
  pendingPlan: PendingPlan | null;
  agenticMode: boolean;
  /** OPT-2 计划步骤 */
  plan: PlanStep[];
  /** OPT-1 策略模式 */
  strategy: string | null;
  /** 流式思考/推理文本 */
  liveReasoning: string;
  /** OPT-3 反思片段（每轮一条） */
  reflections: string[];
  /** FE-3 会话累计 token */
  sessionTokenUsage: TokenUsage;
  /** FE-3 缓存节省 token */
  cacheTokensSaved: number;
  /** FE-3 工件引用 */
  artifacts: ArtifactRef[];
  /** FE-3 上下文压缩提示 */
  compactionNotices: string[];
  /** FE-4 生命周期 */
  lifecycle: AgentLifecycleState;
}

const emptyTokenUsage = (): TokenUsage => ({ prompt: 0, completion: 0, total: 0 });

export const initialChatLiveState: ChatLiveState = {
  liveStreamingText: '',
  liveToolCalls: [],
  pendingPlan: null,
  agenticMode: false,
  plan: [],
  strategy: null,
  liveReasoning: '',
  reflections: [],
  sessionTokenUsage: emptyTokenUsage(),
  cacheTokensSaved: 0,
  artifacts: [],
  compactionNotices: [],
  lifecycle: 'idle',
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
  updatePendingMessageId?: number;
}

export interface ChatReduceResult {
  live: ChatLiveState;
  effects: ChatReduceEffects;
}

function buildStepMessages(
  convId: string,
  data: Record<string, unknown>,
): ChatMessage[] {
  const am = (data.assistant_message as Record<string, unknown>) ?? data;
  const content = (am.content as string) || null;
  const tcs = (am.tool_calls as ChatToolCall[]) ?? null;
  const trs = (data.tool_results as Array<Record<string, unknown>>) ?? [];
  const baseTs = Date.now();
  const newMsgs: ChatMessage[] = [];

  if (content || tcs) {
    newMsgs.push({
      id: -baseTs,
      conversation_id: convId,
      role: 'assistant',
      content,
      tool_calls: tcs,
      tool_call_id: null,
      trace_id: null,
      token_usage: null,
      status: 0 as ChatMessageStatus,
      created_at: new Date().toISOString(),
    });
  }
  trs.forEach((r, i) => {
    newMsgs.push({
      id: -(baseTs + i + 1),
      conversation_id: convId,
      role: 'tool',
      content: String(r.content ?? ''),
      tool_calls: null,
      tool_call_id: (r.tool_call_id as string) ?? '',
      trace_id: null,
      token_usage: null,
      status: 0 as ChatMessageStatus,
      created_at: new Date().toISOString(),
    });
  });
  return newMsgs;
}

/**
 * 纯函数：将 SSE 事件归约为实时 UI 状态（FE-6）。
 * 行为与迁移前 chatStore.handleLiveEvent 保持一致，并扩展 FE-1 新事件。
 */
export function reduceChatEvent(
  live: ChatLiveState,
  event: TraceEvent,
  ctx: ChatReduceContext,
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

    case 'chat.reasoning_delta': {
      const delta = (data.delta as string) ?? '';
      const accumulated = (data.accumulated as string) ?? '';
      next = {
        ...live,
        liveReasoning: delta
          ? live.liveReasoning + delta
          : accumulated || live.liveReasoning,
      };
      break;
    }

    case 'chat.tool_call_start': {
      const callId = (data.call_id as string) ?? '';
      const toolName = (data.tool_name as string) ?? '';
      const args = (data.arguments as Record<string, unknown>) ?? {};
      next = {
        ...live,
        liveToolCalls: [
          ...live.liveToolCalls,
          { callId, toolName, arguments: args, status: 'running' as const },
        ],
      };
      break;
    }

    case 'chat.tool_call_end': {
      const callId = (data.call_id as string) ?? '';
      const ok = (data.ok as boolean) ?? false;
      const result = data.result;
      next = {
        ...live,
        liveToolCalls: live.liveToolCalls.map((tc) =>
          tc.callId === callId
            ? { ...tc, status: ok ? ('completed' as const) : ('failed' as const), result }
            : tc,
        ),
      };
      break;
    }

    case 'chat.tool_call_proposed': {
      const convId = ctx.activeConversationId ?? '';
      const tcs = (data.tool_calls as ToolCall[]) ?? [];
      next = {
        ...live,
        pendingPlan: {
          toolCalls: tcs,
          messageId: 0,
          conversationId: convId,
        },
      };
      break;
    }

    case 'chat.turn_paused': {
      next = { ...live };
      effects.setInFlight = false;
      effects.setActiveTraceId = null;
      effects.refreshMessages = true;
      break;
    }

    case 'chat.turn_end': {
      const usage = data.token_usage as TokenUsage | undefined;
      if (usage) {
        next = {
          ...live,
          sessionTokenUsage: {
            prompt: live.sessionTokenUsage.prompt + (usage.prompt ?? 0),
            completion: live.sessionTokenUsage.completion + (usage.completion ?? 0),
            total: live.sessionTokenUsage.total + (usage.total ?? 0),
          },
          lifecycle: 'idle',
        };
      } else {
        next = { ...live, lifecycle: 'idle' };
      }
      break;
    }

    case 'chat.turn_error':
      next = { ...live, lifecycle: 'idle' };
      break;

    case 'chat.artifact_created': {
      const ref = data.artifact as ArtifactRef | undefined;
      if (ref?.id) {
        next = { ...live, artifacts: [...live.artifacts, ref] };
      }
      break;
    }

    case 'chat.context_compacted': {
      const msg = (data.message as string) ?? (data.reason as string) ?? '';
      if (msg) {
        next = { ...live, compactionNotices: [...live.compactionNotices, msg] };
      }
      break;
    }

    case 'chat.cache_hit': {
      const saved = (data.tokens_saved as number) ?? 0;
      next = { ...live, cacheTokensSaved: live.cacheTokensSaved + saved };
      break;
    }

    case 'chat.lifecycle_changed': {
      const state = (data.state as AgentLifecycleState) ?? live.lifecycle;
      next = { ...live, lifecycle: state };
      break;
    }

    case 'chat.mode_changed': {
      const mode = (data.mode as string) ?? 'chat';
      next = { ...live, agenticMode: mode === 'agentic' };
      break;
    }

    case 'chat.plan_updated': {
      const steps = (data.steps as PlanStep[]) ?? [];
      next = { ...live, plan: steps };
      break;
    }

    case 'chat.reflection': {
      const text = (data.text as string) ?? '';
      if (text) {
        next = { ...live, reflections: [...live.reflections, text] };
      }
      break;
    }

    case 'chat.strategy': {
      const mode = (data.mode as string) ?? null;
      next = { ...live, strategy: mode };
      break;
    }

    // 向后兼容 harness 事件
    case 'think_end': {
      const am = (data.assistant_message as Record<string, unknown>) ?? data;
      const content = (am.content as string) || null;
      if (content) {
        next = { ...live, liveStreamingText: content };
      }
      break;
    }

    case 'act_end': {
      const results =
        (data.tool_results as Array<Record<string, unknown>> | null | undefined) ?? [];
      let toolCalls = live.liveToolCalls;
      for (const r of results) {
        const callId = (r.tool_call_id as string) ?? '';
        const content = String(r.content ?? '');
        toolCalls = toolCalls.map((tc) =>
          tc.callId === callId
            ? { ...tc, status: 'completed' as const, result: content }
            : tc,
        );
      }
      next = { ...live, liveToolCalls: toolCalls };
      break;
    }

    case 'step_end': {
      const conv = ctx.activeConversationId ?? '';
      if (conv) {
        effects.appendMessages = buildStepMessages(conv, data);
      }
      next = { ...live, liveStreamingText: '', liveToolCalls: [] };
      break;
    }

    default:
      break;
  }

  return { live: next, effects };
}
