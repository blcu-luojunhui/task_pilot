import { useEffect, useRef } from 'react';
import { Empty, Typography } from 'antd';
import type { ChatMessage } from '@/api/types';
import type { PendingPlan, ToolCallStatus } from '@/stores/chatStore';
import { MessageBubble } from './MessageBubble';
import { PendingPlanCard } from './PendingPlanCard';
import { StreamingBubble } from './StreamingBubble';
import { ToolCallBlock } from './ToolCallBlock';
import './ChatMessage.css';

interface Props {
  messages: ChatMessage[];
  /** 正在执行中的工具调用 */
  liveToolCalls: ToolCallStatus[];
  /** 待确认的高风险 plan */
  pendingPlan: PendingPlan | null;
  inFlight: boolean;
  agenticMode?: boolean;
  confirmLoading?: boolean;
  onConfirmPlan?: () => void;
  onRejectPlan?: () => void;
}

export function MessageList({
  messages,
  liveToolCalls,
  pendingPlan,
  inFlight,
  agenticMode = false,
  confirmLoading = false,
  onConfirmPlan,
  onRejectPlan,
}: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // 持久化消息 / 工具调用 / pendingPlan 变化时滚到底；
  // liveStreamingText 高频变化由 StreamingBubble 内部 rAF 节流处理。
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
  }, [messages.length, liveToolCalls.length, pendingPlan]);

  const isIdle =
    messages.length === 0 &&
    liveToolCalls.length === 0 &&
    !pendingPlan &&
    !inFlight;

  if (isIdle) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Empty
          description={
            <Typography.Text type="secondary">
              开始对话吧 — TaskPilot agent 可以帮你规划、运行和取消任务
            </Typography.Text>
          }
        />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
      {/* 持久化消息 */}
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}

      {/* 流式实时文本 — 独立订阅 store，隔离高频重渲染 */}
      <StreamingBubble />

      {/* 实时工具调用执行状态 */}
      {liveToolCalls.map((tc, i) => (
        <ToolCallBlock key={tc.callId || `tc-${i}`} toolCall={tc} />
      ))}

      {/* 待确认高风险 plan */}
      {pendingPlan && onConfirmPlan && onRejectPlan && (
        <PendingPlanCard
          toolCalls={pendingPlan.toolCalls}
          loading={confirmLoading}
          onConfirm={onConfirmPlan}
          onReject={onRejectPlan}
        />
      )}

      {/* 等待中指示器 */}
      {inFlight && liveToolCalls.length === 0 && !pendingPlan && (
        <div style={{ display: 'flex', alignItems: 'center', padding: '4px 16px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '8px 16px',
            borderRadius: 14,
            background: '#f6ffed',
            border: '1px solid #b7eb8f',
          }}>
            <div className="thinking-dots">
              <span />
              <span />
              <span />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {agenticMode ? 'Agent 执行中' : 'Agent 思考中'}
            </Typography.Text>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
