import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { theme } from 'antd';
import { CodeBlock } from '@/components/common/CodeBlock';

interface Props {
  content: string;
  isUser?: boolean;
  /** 流式中途容错：闭合未配对的代码围栏 */
  streaming?: boolean;
}

/** 流式中途闭合未配对的 ```，避免布局抖动 */
function streamingSafeMarkdown(content: string, streaming: boolean): string {
  if (!streaming) return content;
  const fences = (content.match(/```/g) || []).length;
  if (fences % 2 !== 0) {
    return `${content}\n\`\`\``;
  }
  return content;
}

/** 流式安全 markdown + 代码高亮（FE-5） */
export function MarkdownContent({ content, streaming = false }: Props) {
  const { token } = theme.useToken();
  const safeContent = streamingSafeMarkdown(content, streaming);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        code({ className, children, ...props }) {
          const isInline = !className;
          if (isInline) {
            return (
              <code
                style={{
                  background: token.colorFillTertiary,
                  padding: '1px 5px',
                  borderRadius: 4,
                  fontSize: '0.88em',
                }}
                {...props}
              >
                {children}
              </code>
            );
          }
          return <CodeBlock className={className}>{children}</CodeBlock>;
        },
        a({ href, children, ...props }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: token.colorSuccess }}
              {...props}
            >
              {children}
            </a>
          );
        },
        th({ children, ...props }) {
          return (
            <th
              style={{
                border: `1px solid ${token.colorBorderSecondary}`,
                padding: '7px 12px',
                background: token.colorFillTertiary,
                fontWeight: 600,
                textAlign: 'left',
              }}
              {...props}
            >
              {children}
            </th>
          );
        },
        td({ children, ...props }) {
          return (
            <td
              style={{
                border: `1px solid ${token.colorBorderSecondary}`,
                padding: '7px 12px',
              }}
              {...props}
            >
              {children}
            </td>
          );
        },
        hr() {
          return (
            <hr
              style={{
                border: 'none',
                borderTop: `1px solid ${token.colorBorderSecondary}`,
              }}
            />
          );
        },
        blockquote({ children, ...props }) {
          return (
            <blockquote
              style={{
                borderLeft: `3px solid ${token.colorPrimaryBorder}`,
                color: token.colorTextSecondary,
              }}
              {...props}
            >
              {children}
            </blockquote>
          );
        },
      }}
    >
      {safeContent}
    </ReactMarkdown>
  );
}
