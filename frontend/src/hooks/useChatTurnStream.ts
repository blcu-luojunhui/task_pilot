import { useEffect, useRef } from 'react';
import { isTerminalEvent } from '@/utils/events';
import type { TraceEvent } from '@/api/types';

export interface UseChatTurnStreamOptions {
  enabled?: boolean;
  onEvent?: (event: TraceEvent) => void;
  onTerminated?: (event: TraceEvent) => void;
}

const MAX_RETRIES = 3;
const MAX_RETRY_DELAY_MS = 8000;

function readToken(): string {
  try {
    const stored = localStorage.getItem('auth-storage');
    if (stored) {
      const parsed = JSON.parse(stored);
      return parsed?.state?.token ?? '';
    }
  } catch { /* ignore */ }
  return '';
}

/**
 * 订阅一轮 chat agent turn 的 SSE 流。
 *
 * 复用 ``/api/task_events/<trace_id>`` —— 因为 chat agent 走的是 task scheduler，
 * 流的事件结构和普通 task 完全一致（think/act/run_end ...）。
 *
 * 与 ``useTraceStream`` 的差异：
 * - 不依赖 traceStore（chat 不应污染 trace 详情页的 store）
 * - 通过 callback 把事件直接交给调用方处理
 * - 终止事件（run_end / run_error / run_stopped / task.finished）触发 onTerminated 后断开
 * - 限制重连次数：trace 已被 close + TTL 过期会一直 404，避免后台无限请求
 */
export function useChatTurnStream(
  traceId: string | null,
  opts: UseChatTurnStreamOptions = {}
): void {
  const enabled = opts.enabled !== false;
  const onEventRef = useRef(opts.onEvent);
  const onTerminatedRef = useRef(opts.onTerminated);
  onEventRef.current = opts.onEvent;
  onTerminatedRef.current = opts.onTerminated;

  useEffect(() => {
    if (!traceId || !enabled) return;

    let aborted = false;
    let es: EventSource | null = null;
    let retryDelay = 1000;
    let retries = 0;
    let receivedAnyEvent = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const terminate = () => {
      aborted = true;
      es?.close();
      onTerminatedRef.current?.({
        sequence: -1,
        type: 'run_stopped',
        trace_id: traceId,
        step: null,
        source: 'client',
        timestamp: new Date().toISOString(),
        data: { reason: 'sse_unavailable' },
      } as unknown as TraceEvent);
    };

    const connect = () => {
      if (aborted) return;
      es = new EventSource(`/api/task_events/${encodeURIComponent(traceId)}?token=${encodeURIComponent(readToken())}`);

      es.onopen = () => {
        retryDelay = 1000;
        retries = 0;
      };

      es.onmessage = (e: MessageEvent) => {
        try {
          receivedAnyEvent = true;
          const event = JSON.parse(e.data) as TraceEvent;
          onEventRef.current?.(event);
          if (isTerminalEvent(event.type)) {
            aborted = true;
            es?.close();
            onTerminatedRef.current?.(event);
          }
        } catch {
          // 忽略不可解析事件
        }
      };

      es.onerror = () => {
        es?.close();
        if (aborted) return;
        // 收到过事件后断开，多半是后端 close_trace 后 EOF —— 当作正常结束
        if (receivedAnyEvent) {
          terminate();
          return;
        }
        retries += 1;
        if (retries >= MAX_RETRIES) {
          // trace 抢跑后仍持续 404 / 持续连不上 —— 放弃，让上层走刷新路径
          terminate();
          return;
        }
        const delay = Math.min(retryDelay * 2, MAX_RETRY_DELAY_MS);
        retryDelay = delay;
        timer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      aborted = true;
      es?.close();
      if (timer !== null) clearTimeout(timer);
    };
  }, [traceId, enabled]);
}
