import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { MessageBubble } from './MessageBubble';
import './ChatMessage.css';

/**
 * 流式输出气泡 —— 单独订阅 chatStore.liveStreamingText，
 * 把 token_delta 高频更新的渲染范围限制在自身，
 * 避免每个 token 都触发整棵 MessageList 重渲染。
 *
 * 滚动通过 rAF 节流，自身 mount 后随内容变化滚到底；
 * behavior: 'auto' 避免 smooth 动画反复打断。
 */
export function StreamingBubble() {
  const text = useChatStore((s) => s.liveStreamingText);
  const ref = useRef<HTMLDivElement>(null);
  const pending = useRef(false);

  useEffect(() => {
    if (!text || pending.current) return;
    pending.current = true;
    requestAnimationFrame(() => {
      ref.current?.scrollIntoView({ block: 'end', behavior: 'auto' });
      pending.current = false;
    });
  }, [text]);

  if (!text) return null;

  return (
    <div ref={ref}>
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
    </div>
  );
}
