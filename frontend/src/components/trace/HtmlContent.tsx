import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

const HTML_RE = /<\/(?:div|span|p|table|html|head|body|a|li|ul|ol|h[1-6]|script|meta|link|title|style|button|form|input|select|option|textarea|iframe|img|br|hr|td|tr|th|section|header|footer|nav|article|aside|main|pre|code|blockquote)>/i;

function looksLikeHtml(content: string): boolean {
  return HTML_RE.test(content);
}

export function HtmlContent({ content, className }: { content: string; className?: string }) {
  const isHtml = useMemo(() => looksLikeHtml(content), [content]);

  if (!isHtml) {
    return (
      <div className={className} style={{ fontSize: 12 }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <iframe
      srcDoc={content}
      sandbox="allow-same-origin"
      style={{
        width: '100%',
        minHeight: 300,
        border: '1px solid var(--border-default)',
        borderRadius: 6,
        backgroundColor: 'var(--surface-card)',
      }}
      title="HTML preview"
    />
  );
}
