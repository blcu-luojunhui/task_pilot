import type { ChatMessage, ChatToolCall, MessagePart, PlanStep } from '@/api/types';

function getTcName(tc: ChatToolCall): string {
  return tc.function?.name ?? tc.name ?? 'unknown';
}

function parsePlanSteps(tc: ChatToolCall): PlanStep[] {
  const raw = tc.function?.arguments ?? tc.arguments ?? '';
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (Array.isArray(parsed?.tasks)) {
      return parsed.tasks.map((t: { goal?: string; status?: string }, i: number) => ({
        id: String(i),
        goal: t.goal ?? `Task ${i + 1}`,
        status: (t.status as PlanStep['status']) ?? 'pending',
      }));
    }
    if (Array.isArray(parsed?.steps)) {
      return parsed.steps as PlanStep[];
    }
  } catch {
    // ignore
  }
  return [];
}

/** 将 ChatMessage 转为有序 parts（FE-5） */
export function buildMessageParts(message: ChatMessage): MessagePart[] {
  const parts: MessagePart[] = [];

  if (message.role === 'tool') {
    if (message.content) {
      parts.push({ kind: 'text', text: message.content });
    }
    return parts;
  }

  if (message.content) {
    parts.push({ kind: 'text', text: message.content });
  }

  if (message.role === 'assistant' && message.tool_calls?.length) {
    for (const tc of message.tool_calls) {
      const name = getTcName(tc);
      if (name === 'plan_tasks') {
        const steps = parsePlanSteps(tc);
        if (steps.length > 0) {
          parts.push({ kind: 'plan', steps });
          continue;
        }
      }
      if (name === 'spawn_subagent' || name === 'subagent') {
        const raw = tc.function?.arguments ?? tc.arguments ?? '{}';
        try {
          const args = typeof raw === 'string' ? JSON.parse(raw) : raw;
          parts.push({
            kind: 'subagent',
            traceId: String(args.child_trace_id ?? args.trace_id ?? ''),
            goal: String(args.goal ?? name),
            summary: args.summary ? String(args.summary) : undefined,
          });
          continue;
        } catch {
          // fall through to tool
        }
      }
      const rawArgs = tc.function?.arguments ?? tc.arguments ?? {};
      parts.push({
        kind: 'tool',
        toolName: name,
        arguments: rawArgs,
        callId: tc.id,
        status: 'completed',
      });
    }
  }

  return parts;
}
