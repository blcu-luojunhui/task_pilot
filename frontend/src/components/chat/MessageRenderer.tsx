import { theme } from 'antd';
import type { MessagePart } from '@/api/types';
import { ArtifactCard } from './ArtifactCard';
import { MarkdownContent } from './MarkdownContent';
import { PlanPanel } from './PlanPanel';
import { ReasoningBlock } from './ReasoningBlock';
import { ToolCallBlock } from './ToolCallBlock';
import { Link } from 'react-router-dom';

interface Props {
  parts: MessagePart[];
  isUser?: boolean;
  streaming?: boolean;
}

function SubAgentPart({
  traceId,
  goal,
  summary,
}: {
  traceId: string;
  goal: string;
  summary?: string;
}) {
  const { token } = theme.useToken();
  if (!traceId) return null;
  return (
    <div
      style={{
        marginTop: 8,
        padding: '8px 12px',
        borderRadius: 8,
        background: token.colorInfoBg,
        border: `1px solid ${token.colorInfoBorder}`,
        fontSize: 13,
      }}
    >
      <div>
        <strong>Sub-agent</strong>: {goal}
      </div>
      {summary && <div style={{ marginTop: 4, opacity: 0.85 }}>{summary}</div>}
      <Link to={`/tasks/${encodeURIComponent(traceId)}`} style={{ fontSize: 12 }}>
        {traceId}
      </Link>
    </div>
  );
}

/** 按 part 类型分派渲染（FE-5） */
export function MessageRenderer({ parts, isUser = false, streaming = false }: Props) {
  const { token } = theme.useToken();

  return (
    <>
      {parts.map((part, i) => {
        switch (part.kind) {
          case 'text':
            return (
              <div
                key={`text-${i}`}
                className="markdown-body"
                aria-live={streaming ? 'polite' : undefined}
              >
                <MarkdownContent content={part.text} isUser={isUser} streaming={streaming} />
                {streaming && <span className="typing-cursor" />}
              </div>
            );
          case 'reasoning':
            return <ReasoningBlock key={`reasoning-${i}`} text={part.text} streaming={streaming} />;
          case 'tool':
            return (
              <div key={`tool-${i}`} style={{ marginTop: 8 }}>
                <ToolCallBlock
                  toolCall={{
                    callId: part.callId ?? `part-${i}`,
                    toolName: part.toolName,
                    arguments:
                      typeof part.arguments === 'string'
                        ? (() => {
                            try {
                              return JSON.parse(part.arguments) as Record<string, unknown>;
                            } catch {
                              return { raw: part.arguments };
                            }
                          })()
                        : part.arguments,
                    status: part.status ?? 'completed',
                    result: part.result,
                  }}
                />
              </div>
            );
          case 'plan':
            return (
              <div key={`plan-${i}`} style={{ marginTop: 8 }}>
                <PlanPanel steps={part.steps} compact />
              </div>
            );
          case 'artifact':
            return (
              <div key={`artifact-${i}`} style={{ marginTop: 8 }}>
                <ArtifactCard artifact={part.ref} />
              </div>
            );
          case 'subagent':
            return (
              <SubAgentPart
                key={`subagent-${i}`}
                traceId={part.traceId}
                goal={part.goal}
                summary={part.summary}
              />
            );
          default:
            return null;
        }
      })}
      {parts.length === 0 && streaming && (
        <span className="typing-cursor" style={{ color: token.colorTextSecondary }} />
      )}
    </>
  );
}
