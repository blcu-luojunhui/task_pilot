import dayjs from 'dayjs';

/** Unix 秒级时间戳 → 本地可读时间 */
export function formatTimestamp(ts: number | null | undefined): string {
  if (!ts) return '-';
  return dayjs.unix(ts).format('YYYY-MM-DD HH:mm:ss');
}

/** ISO 时间字符串 → 本地可读时间 */
export function formatIso(iso: string): string {
  if (!iso) return '-';
  return dayjs(iso).format('YYYY-MM-DD HH:mm:ss');
}

/** 任务起止时间戳 → 持续时长（人类可读） */
export function formatDuration(
  start: number | null | undefined,
  end: number | null | undefined
): string {
  if (!start) return '-';
  const finish = end ?? Math.floor(Date.now() / 1000);
  return formatSeconds(finish - start);
}

/** 秒数 → "1m 23s" */
export function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '-';
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

/** 截断 trace_id 显示前后段，中间省略 */
export function truncateTraceId(traceId: string, head = 12, tail = 6): string {
  if (!traceId || traceId.length <= head + tail + 3) return traceId;
  return `${traceId.slice(0, head)}…${traceId.slice(-tail)}`;
}
