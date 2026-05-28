import { create } from 'zustand';
import {
  cancelChatTurn,
  confirmChatPlan,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  sendChatMessage,
  updateConversationTitle,
} from '@/api/chat';
import type {
  ChatConversation,
  ChatMessage,
  ChatMessageStatus,
  ChatToolCall,
  ToolCall,
  TraceEvent,
} from '@/api/types';

// ── 实时工具调用状态 ──────────────────────────────────────────

export interface ToolCallStatus {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'completed' | 'failed';
  result?: unknown;
}

// ── 待确认 plan ──────────────────────────────────────────────

export interface PendingPlan {
  messageId: number;
  toolCalls: ToolCall[];
  conversationId: string;
}

// ── Store 状态 ───────────────────────────────────────────────

interface ChatStoreState {
  // 列表
  conversations: ChatConversation[];
  conversationsLoading: boolean;
  conversationsTotal: number;

  // 当前会话
  activeConversationId: string | null;
  activeConversation: ChatConversation | null;
  activeMessages: ChatMessage[];
  activeLoading: boolean;
  activeTraceId: string | null;
  inFlight: boolean;

  // 流式实时状态
  /** chat.token_delta 累积的实时文本 */
  liveStreamingText: string;
  /** 正在执行中的工具调用 */
  liveToolCalls: ToolCallStatus[];
  /** 当前待确认的高风险 plan（触发 PlanCard 渲染） */
  pendingPlan: PendingPlan | null;
  /** 当前是否处于 agentic 模式 */
  agenticMode: boolean;

  // 操作
  fetchConversations: () => Promise<void>;
  selectConversation: (id: string | null) => Promise<void>;
  startNewConversation: () => Promise<string>;
  sendMessage: (content: string) => Promise<void>;
  cancelCurrentTurn: () => Promise<void>;
  confirmPlan: (action: 'confirm' | 'reject') => Promise<void>;
  refreshActiveMessages: () => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  removeConversation: (id: string) => Promise<void>;

  /** SSE 回调 — 处理 chat.* 事件 */
  handleLiveEvent: (event: TraceEvent) => void;
  /** SSE 终止后刷新 */
  onTurnTerminated: () => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  conversations: [],
  conversationsLoading: false,
  conversationsTotal: 0,

  activeConversationId: null,
  activeConversation: null,
  activeMessages: [],
  activeLoading: false,
  activeTraceId: null,
  inFlight: false,
  liveStreamingText: '',
  liveToolCalls: [],
  pendingPlan: null,
  agenticMode: false,

  // ── 会话操作 ──────────────────────────────────────────────

  fetchConversations: async () => {
    set({ conversationsLoading: true });
    try {
      const data = await listConversations({ limit: 50 });
      set({
        conversations: data.items,
        conversationsTotal: data.total,
        conversationsLoading: false,
      });
    } catch {
      set({ conversationsLoading: false });
    }
  },

  selectConversation: async (id) => {
    if (!id) {
      set({
        activeConversationId: null,
        activeConversation: null,
        activeMessages: [],
        activeTraceId: null,
        inFlight: false,
        liveStreamingText: '',
        liveToolCalls: [],
        pendingPlan: null,
      });
      return;
    }
    if (get().activeConversationId === id && get().activeMessages.length > 0) return;
    set({
      activeConversationId: id,
      activeLoading: true,
      activeMessages: [],
      activeTraceId: null,
      liveStreamingText: '',
      liveToolCalls: [],
      pendingPlan: null,
    });
    try {
      const detail = await getConversation(id);
      set({
        activeConversation: detail.conversation,
        activeMessages: detail.messages,
        activeLoading: false,
      });
    } catch {
      set({ activeLoading: false });
    }
  },

  startNewConversation: async () => {
    const conv = await createConversation();
    set((s) => ({
      conversations: [conv, ...s.conversations],
      activeConversationId: conv.conversation_id,
      activeConversation: conv,
      activeMessages: [],
      activeTraceId: null,
      inFlight: false,
      liveStreamingText: '',
      liveToolCalls: [],
      pendingPlan: null,
    }));
    return conv.conversation_id;
  },

  sendMessage: async (content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    let convId = get().activeConversationId;
    if (!convId) {
      convId = await get().startNewConversation();
    }

    const optimisticUser: ChatMessage = {
      id: -Date.now(),
      conversation_id: convId,
      role: 'user',
      content: trimmed,
      tool_calls: null,
      tool_call_id: null,
      trace_id: null,
      token_usage: null,
      status: 0 as ChatMessageStatus,
      created_at: new Date().toISOString(),
    };
    set((s) => ({
      activeMessages: [...s.activeMessages, optimisticUser],
      inFlight: true,
      liveStreamingText: '',
      liveToolCalls: [],
      pendingPlan: null,
    }));

    try {
      const response = await sendChatMessage(convId, trimmed);
      set({ activeTraceId: response.trace_id });
    } catch {
      set((s) => ({
        activeMessages: s.activeMessages.filter((m) => m.id !== optimisticUser.id),
        inFlight: false,
        liveStreamingText: '',
        liveToolCalls: [],
      }));
    }
  },

  cancelCurrentTurn: async () => {
    const { activeConversationId, activeTraceId } = get();
    if (!activeConversationId || !activeTraceId) return;
    try {
      await cancelChatTurn(activeConversationId, activeTraceId);
    } catch {
      // 后端 message 提示
    }
  },

  confirmPlan: async (action) => {
    const { pendingPlan, activeConversationId } = get();
    if (!pendingPlan || !activeConversationId) return;

    set({ inFlight: true, pendingPlan: null, liveToolCalls: [], liveStreamingText: '' });

    try {
      const response = await confirmChatPlan(activeConversationId, {
        message_id: pendingPlan.messageId,
        action,
      });

      if (action === 'confirm' && response.code === 0 && response.trace_id) {
        set({ activeTraceId: response.trace_id });
      } else if (action === 'reject' && response.code === 0) {
        await get().refreshActiveMessages();
        set({ inFlight: false });
      }
    } catch {
      set({ inFlight: false });
    }
  },

  refreshActiveMessages: async () => {
    const id = get().activeConversationId;
    if (!id) return;
    try {
      const detail = await getConversation(id);
      set((s) => ({
        activeConversation: detail.conversation,
        activeMessages: detail.messages,
        liveStreamingText: s.inFlight ? s.liveStreamingText : '',
        liveToolCalls: s.inFlight ? s.liveToolCalls : [],
      }));
    } catch {
      // 忽略
    }
  },

  renameConversation: async (id, title) => {
    await updateConversationTitle(id, title);
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.conversation_id === id ? { ...c, title } : c
      ),
      activeConversation:
        s.activeConversationId === id && s.activeConversation
          ? { ...s.activeConversation, title }
          : s.activeConversation,
    }));
  },

  removeConversation: async (id) => {
    try {
      await deleteConversation(id);
    } catch {
      // API 失败则不更新本地状态
      return;
    }

    const state = get();
    const filtered = state.conversations.filter((c) => c.conversation_id !== id);
    const isActive = state.activeConversationId === id;

    set({
      conversations: filtered,
      ...(isActive
        ? {
            activeConversationId: null,
            activeConversation: null,
            activeMessages: [],
            activeTraceId: null,
            inFlight: false,
            liveStreamingText: '',
            liveToolCalls: [],
            pendingPlan: null,
          }
        : {}),
    });

    // 删除的是当前活跃会话 → 自动选下一个或新建
    if (isActive) {
      if (filtered.length > 0) {
        await get().selectConversation(filtered[0].conversation_id);
      } else {
        await get().startNewConversation();
      }
    }
  },

  // ── SSE 事件处理 ───────────────────────────────────────────

  handleLiveEvent: (event: TraceEvent) => {
    const data = event.data ?? {};

    switch (event.type) {
      case 'chat.token_delta': {
        const delta = (data.delta as string) ?? '';
        // 后端只发增量；fallback：兼容旧的 accumulated 字段
        if (delta) {
          set((s) => ({ liveStreamingText: s.liveStreamingText + delta }));
        } else {
          const accumulated = (data.accumulated as string) ?? '';
          if (accumulated) set({ liveStreamingText: accumulated });
        }
        break;
      }

      case 'chat.tool_call_start': {
        const callId = (data.call_id as string) ?? '';
        const toolName = (data.tool_name as string) ?? '';
        const args = (data.arguments as Record<string, unknown>) ?? {};
        set((s) => ({
          liveToolCalls: [
            ...s.liveToolCalls,
            { callId, toolName, arguments: args, status: 'running' as const },
          ],
        }));
        break;
      }

      case 'chat.tool_call_end': {
        const callId = (data.call_id as string) ?? '';
        const ok = (data.ok as boolean) ?? false;
        const result = data.result;
        set((s) => ({
          liveToolCalls: s.liveToolCalls.map((tc) =>
            tc.callId === callId
              ? { ...tc, status: ok ? 'completed' as const : 'failed' as const, result }
              : tc
          ),
        }));
        break;
      }

      case 'chat.tool_call_proposed': {
        const convId = get().activeConversationId ?? '';
        const tcs = (data.tool_calls as ToolCall[]) ?? [];
        set({
          pendingPlan: {
            toolCalls: tcs,
            messageId: 0, // 等 turn_paused 后 refresh 拿到真实 messageId
            conversationId: convId,
          },
        });
        break;
      }

      case 'chat.turn_paused': {
        set({ inFlight: false, activeTraceId: null });
        // 刷新消息列表获取 pending 消息的真实 messageId
        void get().refreshActiveMessages().finally(() => {
          const msgs = get().activeMessages;
          const pending = msgs.find(
            (m) => m.role === 'assistant' && m.status === 1
          );
          if (pending && get().pendingPlan) {
            set({
              pendingPlan: { ...get().pendingPlan!, messageId: pending.id },
            });
          }
        });
        break;
      }

      case 'chat.turn_end': {
        // 终态由 onTurnTerminated 处理
        break;
      }

      case 'chat.turn_error': {
        break;
      }

      case 'chat.mode_changed': {
        const mode = (data.mode as string) ?? 'chat';
        set({ agenticMode: mode === 'agentic' });
        break;
      }

      // 向后兼容：保留旧 harness 事件的解析能力
      case 'think_end': {
        const am = (data.assistant_message as Record<string, unknown>) ?? data;
        const content = (am.content as string) || null;
        if (content) {
          set({ liveStreamingText: content });
        }
        break;
      }

      case 'act_end': {
        const results = (data.tool_results as Array<Record<string, unknown>> | null | undefined) ?? [];
        results.forEach((r) => {
          const callId = (r.tool_call_id as string) ?? '';
          const content = String(r.content ?? '');
          set((s) => ({
            liveToolCalls: s.liveToolCalls.map((tc) =>
              tc.callId === callId
                ? { ...tc, status: 'completed' as const, result: content }
                : tc
            ),
          }));
        });
        break;
      }

      case 'step_end': {
        // harness 单步结束 — 快照到 activeMessages
        const am = (data.assistant_message as Record<string, unknown>) ?? data;
        const content = (am.content as string) || null;
        const tcs = (am.tool_calls as ChatToolCall[]) ?? null;
        const trs = (data.tool_results as Array<Record<string, unknown>>) ?? [];

        const conv = get().activeConversationId ?? '';
        const baseTs = Date.now();
        const newMsgs: ChatMessage[] = [];
        if (content || tcs) {
          newMsgs.push({
            id: -baseTs,
            conversation_id: conv,
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
            conversation_id: conv,
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

        set((s) => ({
          activeMessages: [...s.activeMessages, ...newMsgs],
          liveStreamingText: '',
          liveToolCalls: [],
        }));
        break;
      }

      default:
        break;
    }
  },

  onTurnTerminated: async () => {
    await get().refreshActiveMessages();
    const state = get();
    // 首次对话完成后，用第一条用户消息自动命名
    const conv = state.activeConversation;
    if (conv && !conv.title) {
      const firstUser = state.activeMessages.find((m) => m.role === 'user');
      if (firstUser?.content) {
        const autoTitle = firstUser.content.slice(0, 30);
        try {
          await updateConversationTitle(conv.conversation_id, autoTitle);
          set((s) => ({
            activeConversation: s.activeConversation
              ? { ...s.activeConversation, title: autoTitle }
              : null,
            conversations: s.conversations.map((c) =>
              c.conversation_id === conv.conversation_id
                ? { ...c, title: autoTitle }
                : c
            ),
          }));
        } catch {
          // 忽略
        }
      }
    }
    set({
      inFlight: false,
      activeTraceId: null,
      liveStreamingText: '',
      liveToolCalls: [],
      pendingPlan: null,
    });
    void get().fetchConversations();
  },

  reset: () =>
    set({
      conversations: [],
      conversationsLoading: false,
      conversationsTotal: 0,
      activeConversationId: null,
      activeConversation: null,
      activeMessages: [],
      activeLoading: false,
      activeTraceId: null,
      inFlight: false,
      liveStreamingText: '',
      liveToolCalls: [],
      pendingPlan: null,
    }),
}));
