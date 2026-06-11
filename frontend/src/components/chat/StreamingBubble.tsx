import { useChatStore } from '@/stores/chatStore';
import { MessageBubble } from './MessageBubble';
import './ChatMessage.css';

/**
 * 流式输出气泡 —— 单独订阅 liveStreamingText，隔离高频重渲染（FE-5）。
 * 滚动由父级 StickToBottom 统一处理。
 */
export function StreamingBubble() {
  const text = useChatStore((s) => s.liveStreamingText);

  if (!text) return null;

  return (
    <MessageBubble
      streaming
      message={{
        id: -1,
        conversation_id: '',
        role: 'assistant',
        content: text,
        tool_calls: null,
        tool_call_id: null,
        trace_id: null,
        token_usage: null,
        status: 0,
        created_at: new Date().toISOString(),
      }}
    />
  );
}
