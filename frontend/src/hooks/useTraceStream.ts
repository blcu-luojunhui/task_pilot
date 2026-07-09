import { useEffect, useRef, useState } from 'react';
import { useTraceStore } from '@/stores/traceStore';
import { isTerminalEvent } from '@/utils/events';
import type { TraceEvent } from '@/api/types';

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

const MAX_RETRIES = 5;
const MAX_RETRY_DELAY_MS = 30_000;

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

interface UseTraceStreamOptions {
  enabled?: boolean;
}

/**
 * SSE 订阅一条 trace 的实时事件流。
 *
 * 特性：
 * - 自动重连（指数退避 1s → 2s → 4s → ... → 30s 封顶）
 * - 检测到终止事件（run_end / run_error / run_stopped / task.finished）后停止重连
 * - 通过 traceStore.appendEvent 去重写入，与 history API 无缝拼接
 * - 组件卸载时自动断开
 */
export function useTraceStream(
  traceId: string | null,
  opts: UseTraceStreamOptions = {}
): StreamStatus {
  const appendEvent = useTraceStore((s) => s.appendEvent);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const enabled = opts.enabled !== false;

  // 用 ref 保持最新的 appendEvent 引用，避免 useEffect 重连
  const appendEventRef = useRef(appendEvent);
  appendEventRef.current = appendEvent;

  useEffect(() => {
    if (!traceId || !enabled) {
      setStatus('idle');
      return;
    }

    let aborted = false;
    let es: EventSource | null = null;
    let retryDelay = 1000;
    let retries = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (aborted) return;
      setStatus('connecting');

      es = new EventSource(`/api/task_events/${encodeURIComponent(traceId)}?token=${encodeURIComponent(readToken())}`);

      es.onopen = () => {
        retryDelay = 1000;
        setStatus('open');
      };

      es.onmessage = (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data) as TraceEvent;
          appendEventRef.current(event);
          if (isTerminalEvent(event.type)) {
            aborted = true;
            es?.close();
            setStatus('closed');
          }
        } catch {
          // 忽略无法解析的事件
        }
      };

      es.onerror = () => {
        es?.close();
        if (aborted) return;

        retries += 1;
        if (retries >= MAX_RETRIES) {
          setStatus('error');
          return;
        }

        setStatus('error');
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

  return status;
}
