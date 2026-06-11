import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  updateConversationTitle,
} from '@/api/chat';
import { chatKeys } from '@/api/queryKeys';

export function useConversationsQuery() {
  return useQuery({
    queryKey: chatKeys.conversations(),
    queryFn: ({ signal }) => listConversations({ limit: 50 }, { signal }),
  });
}

export function useConversationQuery(conversationId: string | null) {
  return useQuery({
    queryKey: chatKeys.conversation(conversationId ?? ''),
    queryFn: ({ signal }) => getConversation(conversationId!, {}, { signal }),
    enabled: Boolean(conversationId),
  });
}

export function useCreateConversationMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => createConversation(),
    onSuccess: (conv) => {
      qc.setQueryData(chatKeys.conversation(conv.conversation_id), {
        conversation: conv,
        messages: [],
      });
      void qc.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}

export function useDeleteConversationMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}

export function useRenameConversationMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      updateConversationTitle(id, title),
    onSuccess: (_, { id }) => {
      void qc.invalidateQueries({ queryKey: chatKeys.conversations() });
      void qc.invalidateQueries({ queryKey: chatKeys.conversation(id) });
    },
  });
}
