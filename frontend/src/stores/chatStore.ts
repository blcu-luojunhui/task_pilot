import { create } from 'zustand';
import {
  cancelChatTurn,
  createConversation,
  deleteConversation,
  sendChatMessage,
  updateConversationTitle,
} from '@/api/chat';
import { chatKeys } from '@/api/queryKeys';
import type {
  ChatMessage,
  ChatMessageStatus,
  ConversationDetailData,
  ListConversationsData,
  TokenUsage,
  TraceEvent,
} from '@/api/types';
import { queryClient } from '@/lib/queryClient';
import {
  initialChatLiveState,
  reduceChatEvent,
  type ChatLiveState,
} from '@/stores/chat/reducer';

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
  sessionTokenUsage: TokenUsage;
  cacheTokensSaved: number;

  // 消息选择
  selectedMessageIds: Set<number>;
  toggleMessageSelection: (messageId: number) => void;
  clearSelection: () => void;

  selectConversation: (id: string | null) => void;
  createAndSelectConversation: () => Promise<string>;
  sendMessage: (content: string) => Promise<void>;
  cancelCurrentTurn: () => Promise<void>;
  refreshActiveMessages: () => void;
  renameConversation: (id: string, title: string) => Promise<void>;
  removeConversation: (id: string) => Promise<string | null>;
  handleLiveEvent: (event: TraceEvent) => void;
  onTurnTerminated: () => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  activeConversationId: null,
  activeTraceId: null,
  inFlight: false,
  ...initialChatLiveState,
  selectedMessageIds: new Set<number>(),

  selectConversation: (id) => {
    if (!id) {
      set({
        activeConversationId: null,
        activeTraceId: null,
        inFlight: false,
        ...initialChatLiveState,
        selectedMessageIds: new Set<number>(),
      });
      return;
    }
    if (get().activeConversationId === id) return;
    set({
      activeConversationId: id,
      activeTraceId: null,
      ...initialChatLiveState,
      selectedMessageIds: new Set<number>(),
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
      selectedMessageIds: new Set<number>(),
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
      selectedMessageIds: new Set<number>(),
    });

    try {
      const response = await sendChatMessage(convId, trimmed);
      set({ activeTraceId: response.trace_id });
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

  toggleMessageSelection: (messageId: number) =>
    set((s) => {
      const next = new Set(s.selectedMessageIds);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return { selectedMessageIds: next };
    }),

  clearSelection: () => set({ selectedMessageIds: new Set<number>() }),

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

    const list = queryClient.getQueryData<ListConversationsData>(chatKeys.conversations());
    const remaining = (list?.items ?? []).filter((c) => c.conversation_id !== id);

    set({
      activeConversationId: null,
      activeTraceId: null,
      inFlight: false,
      ...initialChatLiveState,
      selectedMessageIds: new Set<number>(),
    });

    if (remaining.length > 0) {
      const nextId = remaining[0].conversation_id;
      get().selectConversation(nextId);
      return nextId;
    }

    return get().createAndSelectConversation();
  },

  handleLiveEvent: (event: TraceEvent) => {
    const state = get();
    const liveSnapshot: ChatLiveState = {
      liveStreamingText: state.liveStreamingText,
      sessionTokenUsage: state.sessionTokenUsage,
      cacheTokensSaved: state.cacheTokensSaved,
    };

    const { live, effects } = reduceChatEvent(liveSnapshot, event, {
      activeConversationId: state.activeConversationId,
    });

    const patch: Partial<ChatStoreState> = {
      liveStreamingText: live.liveStreamingText,
      sessionTokenUsage: live.sessionTokenUsage,
      cacheTokensSaved: live.cacheTokensSaved,
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
      const firstUser = messages.find((m: ChatMessage) => m.role === 'user');
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
      selectedMessageIds: new Set<number>(),
    }),
}));
