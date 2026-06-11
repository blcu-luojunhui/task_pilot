import { create } from 'zustand';
import {
  pauseAgent,
  resumeAgent,
  saveSnapshot,
  stopAgent,
} from '@/api/agentControl';
import {
  cancelChatTurn,
  confirmChatPlan,
  createConversation,
  deleteConversation,
  sendChatMessage,
  updateConversationTitle,
} from '@/api/chat';
import { chatKeys } from '@/api/queryKeys';
import type {
  AgentLifecycleState,
  ArtifactRef,
  ChatMessage,
  ChatMessageStatus,
  ConversationDetailData,
  PlanStep,
  TokenUsage,
  TraceEvent,
} from '@/api/types';
import { queryClient } from '@/lib/queryClient';
import {
  initialChatLiveState,
  reduceChatEvent,
  type ChatLiveState,
  type PendingPlan,
  type ToolCallStatus,
} from '@/stores/chat/reducer';

export type { PendingPlan, ToolCallStatus };

function invalidateConversation(id: string) {
  void queryClient.invalidateQueries({ queryKey: chatKeys.conversation(id) });
}

function invalidateConversations() {
  void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
}

function patchConversation(
  id: string,
  updater: (prev: ConversationDetailData | undefined) => ConversationDetailData | undefined,
) {
  queryClient.setQueryData<ConversationDetailData>(chatKeys.conversation(id), updater);
}

interface ChatStoreState {
  activeConversationId: string | null;
  activeTraceId: string | null;
  inFlight: boolean;

  liveStreamingText: string;
  liveToolCalls: ToolCallStatus[];
  pendingPlan: PendingPlan | null;
  agenticMode: boolean;
  plan: PlanStep[];
  strategy: string | null;
  liveReasoning: string;
  reflections: string[];
  sessionTokenUsage: TokenUsage;
  cacheTokensSaved: number;
  artifacts: ArtifactRef[];
  compactionNotices: string[];
  lifecycle: AgentLifecycleState;
  controlLoading: boolean;

  selectConversation: (id: string | null) => void;
  createAndSelectConversation: () => Promise<string>;
  sendMessage: (content: string) => Promise<void>;
  cancelCurrentTurn: () => Promise<void>;
  confirmPlan: (action: 'confirm' | 'reject') => Promise<void>;
  refreshActiveMessages: () => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  removeConversation: (id: string) => Promise<string | null>;
  pauseCurrentAgent: () => Promise<void>;
  resumeCurrentAgent: () => Promise<void>;
  stopCurrentAgent: () => Promise<void>;
  saveCurrentSnapshot: () => Promise<void>;
  handleLiveEvent: (event: TraceEvent) => void;
  onTurnTerminated: () => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  activeConversationId: null,
  activeTraceId: null,
  inFlight: false,
  ...initialChatLiveState,
  controlLoading: false,

  selectConversation: (id) => {
    if (!id) {
      set({
        activeConversationId: null,
        activeTraceId: null,
        inFlight: false,
        ...initialChatLiveState,
      });
      return;
    }
    if (get().activeConversationId === id) return;
    set({
      activeConversationId: id,
      activeTraceId: null,
      ...initialChatLiveState,
    });
  },

  createAndSelectConversation: async () => {
    const conv = await createConversation();
    patchConversation(conv.conversation_id, () => ({
      conversation: conv,
      messages: [],
    }));
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    set({
      activeConversationId: conv.conversation_id,
      activeTraceId: null,
      inFlight: false,
      ...initialChatLiveState,
    });
    return conv.conversation_id;
  },

  sendMessage: async (content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    let convId = get().activeConversationId;
    if (!convId) {
      convId = await get().createAndSelectConversation();
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

    patchConversation(convId, (prev) =>
      prev
        ? { ...prev, messages: [...prev.messages, optimisticUser] }
        : { conversation: { conversation_id: convId } as ConversationDetailData['conversation'], messages: [optimisticUser] },
    );

    set({
      inFlight: true,
      ...initialChatLiveState,
      lifecycle: 'running',
    });

    try {
      const response = await sendChatMessage(convId, trimmed);
      set({ activeTraceId: response.trace_id, lifecycle: 'running' });
    } catch {
      patchConversation(convId, (prev) =>
        prev
          ? { ...prev, messages: prev.messages.filter((m) => m.id !== optimisticUser.id) }
          : prev,
      );
      set({ inFlight: false, ...initialChatLiveState });
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

    set({
      inFlight: true,
      pendingPlan: null,
      liveToolCalls: [],
      liveStreamingText: '',
      liveReasoning: '',
    });

    try {
      const response = await confirmChatPlan(activeConversationId, {
        message_id: pendingPlan.messageId,
        action,
      });

      if (action === 'confirm' && response.code === 0 && response.trace_id) {
        set({ activeTraceId: response.trace_id, lifecycle: 'running' });
      } else if (action === 'reject' && response.code === 0) {
        get().refreshActiveMessages();
        set({ inFlight: false });
      }
    } catch {
      set({ inFlight: false });
    }
  },

  refreshActiveMessages: () => {
    const id = get().activeConversationId;
    if (id) invalidateConversation(id);
  },

  renameConversation: async (id, title) => {
    await updateConversationTitle(id, title);
    patchConversation(id, (prev) =>
      prev ? { ...prev, conversation: { ...prev.conversation, title } } : prev,
    );
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
  },

  removeConversation: async (id) => {
    try {
      await deleteConversation(id);
    } catch {
      return null;
    }

    queryClient.removeQueries({ queryKey: chatKeys.conversation(id) });
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });

    const isActive = get().activeConversationId === id;
    if (!isActive) return null;

    const list = queryClient.getQueryData<{ items: { conversation_id: string }[] }>(
      chatKeys.conversations(),
    );
    const remaining = (list?.items ?? []).filter((c) => c.conversation_id !== id);

    set({
      activeConversationId: null,
      activeTraceId: null,
      inFlight: false,
      ...initialChatLiveState,
    });

    if (remaining.length > 0) {
      const nextId = remaining[0].conversation_id;
      get().selectConversation(nextId);
      return nextId;
    }

    return get().createAndSelectConversation();
  },

  pauseCurrentAgent: async () => {
    const traceId = get().activeTraceId;
    if (!traceId) return;
    set({ controlLoading: true });
    try {
      await pauseAgent(traceId);
      set({ lifecycle: 'paused', inFlight: false });
    } finally {
      set({ controlLoading: false });
    }
  },

  resumeCurrentAgent: async () => {
    const traceId = get().activeTraceId;
    if (!traceId) return;
    set({ controlLoading: true });
    try {
      await resumeAgent(traceId);
      set({ lifecycle: 'running', inFlight: true });
    } finally {
      set({ controlLoading: false });
    }
  },

  stopCurrentAgent: async () => {
    const traceId = get().activeTraceId;
    if (!traceId) return;
    set({ controlLoading: true });
    try {
      await stopAgent(traceId);
      set({ lifecycle: 'stopped', inFlight: false, activeTraceId: null });
      get().refreshActiveMessages();
    } finally {
      set({ controlLoading: false });
    }
  },

  saveCurrentSnapshot: async () => {
    const traceId = get().activeTraceId;
    if (!traceId) return;
    set({ controlLoading: true });
    try {
      await saveSnapshot(traceId);
    } finally {
      set({ controlLoading: false });
    }
  },

  handleLiveEvent: (event: TraceEvent) => {
    const state = get();
    const liveSnapshot: ChatLiveState = {
      liveStreamingText: state.liveStreamingText,
      liveToolCalls: state.liveToolCalls,
      pendingPlan: state.pendingPlan,
      agenticMode: state.agenticMode,
      plan: state.plan,
      strategy: state.strategy,
      liveReasoning: state.liveReasoning,
      reflections: state.reflections,
      sessionTokenUsage: state.sessionTokenUsage,
      cacheTokensSaved: state.cacheTokensSaved,
      artifacts: state.artifacts,
      compactionNotices: state.compactionNotices,
      lifecycle: state.lifecycle,
    };

    const { live, effects } = reduceChatEvent(liveSnapshot, event, {
      activeConversationId: state.activeConversationId,
    });

    const patch: Partial<ChatStoreState> = {
      liveStreamingText: live.liveStreamingText,
      liveToolCalls: live.liveToolCalls,
      pendingPlan: live.pendingPlan,
      agenticMode: live.agenticMode,
      plan: live.plan,
      strategy: live.strategy,
      liveReasoning: live.liveReasoning,
      reflections: live.reflections,
      sessionTokenUsage: live.sessionTokenUsage,
      cacheTokensSaved: live.cacheTokensSaved,
      artifacts: live.artifacts,
      compactionNotices: live.compactionNotices,
      lifecycle: live.lifecycle,
    };

    if (effects.setInFlight !== undefined) patch.inFlight = effects.setInFlight;
    if (effects.setActiveTraceId !== undefined) patch.activeTraceId = effects.setActiveTraceId;

    if (effects.appendMessages?.length && state.activeConversationId) {
      const convId = state.activeConversationId;
      patchConversation(convId, (prev) =>
        prev ? { ...prev, messages: [...prev.messages, ...effects.appendMessages!] } : prev,
      );
    }

    set(patch);

    if (effects.refreshMessages) {
      get().refreshActiveMessages();
      queueMicrotask(() => {
        const convId = get().activeConversationId;
        if (!convId) return;
        const detail = queryClient.getQueryData<ConversationDetailData>(
          chatKeys.conversation(convId),
        );
        const pending = detail?.messages.find(
          (m) => m.role === 'assistant' && m.status === 1,
        );
        if (pending && get().pendingPlan) {
          set({ pendingPlan: { ...get().pendingPlan!, messageId: pending.id } });
        }
      });
    }
  },

  onTurnTerminated: async () => {
    const convId = get().activeConversationId;
    if (convId) invalidateConversation(convId);
    invalidateConversations();

    const detail = convId
      ? queryClient.getQueryData<ConversationDetailData>(chatKeys.conversation(convId))
      : undefined;
    const conv = detail?.conversation;
    const messages = detail?.messages ?? [];

    if (conv && !conv.title && convId) {
      const firstUser = messages.find((m) => m.role === 'user');
      if (firstUser?.content) {
        const autoTitle = firstUser.content.slice(0, 30);
        try {
          await updateConversationTitle(convId, autoTitle);
          patchConversation(convId, (prev) =>
            prev ? { ...prev, conversation: { ...prev.conversation, title: autoTitle } } : prev,
          );
          invalidateConversations();
        } catch {
          // 忽略
        }
      }
    }

    set({
      inFlight: false,
      activeTraceId: null,
      ...initialChatLiveState,
    });
  },

  reset: () =>
    set({
      activeConversationId: null,
      activeTraceId: null,
      inFlight: false,
      ...initialChatLiveState,
      controlLoading: false,
    }),
}));
