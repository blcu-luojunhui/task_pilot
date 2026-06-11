import { apiClient, unwrap } from './client';
import type {
  ApiRequestOptions,
  ChatConversation,
  ConfirmPlanRequest,
  ConfirmPlanResponse,
  ConversationDetailData,
  ListConversationsData,
  SendChatMessageResponse,
} from './types';

export interface ListConversationsParams {
  limit?: number;
  offset?: number;
  /** 0=active, 1=archived, 'all'=不过滤（仅排除 DELETED） */
  status?: number | 'all';
}

export interface CreateConversationPayload {
  title?: string;
  metadata?: Record<string, unknown>;
}

export interface GetConversationParams {
  message_limit?: number;
  before_id?: number;
}

export async function createConversation(
  payload: CreateConversationPayload = {}
): Promise<ChatConversation> {
  return unwrap(
    apiClient.post<{ data: ChatConversation }>('/chat/conversations', payload)
  );
}

export async function listConversations(
  params: ListConversationsParams = {},
  options?: ApiRequestOptions,
): Promise<ListConversationsData> {
  return unwrap(
    apiClient.get<{ data: ListConversationsData }>('/chat/conversations', {
      params,
      signal: options?.signal,
    }),
  );
}

export async function getConversation(
  conversationId: string,
  params: GetConversationParams = {},
  options?: ApiRequestOptions,
): Promise<ConversationDetailData> {
  return unwrap(
    apiClient.get<{ data: ConversationDetailData }>(
      `/chat/conversations/${encodeURIComponent(conversationId)}`,
      { params, signal: options?.signal },
    ),
  );
}

export async function updateConversationTitle(
  conversationId: string,
  title: string
): Promise<{ conversation_id: string; title: string }> {
  return unwrap(
    apiClient.patch<{ data: { conversation_id: string; title: string } }>(
      `/chat/conversations/${encodeURIComponent(conversationId)}`,
      { title }
    )
  );
}

export async function deleteConversation(
  conversationId: string
): Promise<{ conversation_id: string; deleted: boolean }> {
  return unwrap(
    apiClient.delete<{ data: { conversation_id: string; deleted: boolean } }>(
      `/chat/conversations/${encodeURIComponent(conversationId)}`
    )
  );
}

/** 发消息 — 后端启动 chat.agent_turn task，返回 trace_id 用于订阅 SSE */
export async function sendChatMessage(
  conversationId: string,
  userMessage: string
): Promise<SendChatMessageResponse> {
  const response = await apiClient.post<SendChatMessageResponse>(
    `/chat/conversations/${encodeURIComponent(conversationId)}/messages`,
    { user_message: userMessage }
  );
  return response.data;
}

export async function cancelChatTurn(
  conversationId: string,
  traceId: string
): Promise<unknown> {
  return unwrap(
    apiClient.post<{ data: unknown }>(
      `/chat/conversations/${encodeURIComponent(conversationId)}/cancel`,
      { trace_id: traceId }
    )
  );
}

export async function confirmChatPlan(
  conversationId: string,
  payload: ConfirmPlanRequest
): Promise<ConfirmPlanResponse> {
  const response = await apiClient.post<ConfirmPlanResponse>(
    `/chat/conversations/${encodeURIComponent(conversationId)}/confirm`,
    payload
  );
  return response.data;
}
