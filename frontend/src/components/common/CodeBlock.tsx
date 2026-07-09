import { useCallback, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  className?: string;
  children: React.ReactNode;
}

/** 从 React children 中递归提取纯文本（rehype-highlight 会生成 hljs span 嵌套） */
function extractText(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (node && typeof node === 'object' && 'props' in node) {
    return extractText((node as React.ReactElement).props.children);
  }
  return '';
}

/** 带语言标签与复制按钮的代码块（兼容 rehype-highlight 生成的 React 元素 children） */
export function CodeBlock({ className, children }: Props) {
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLElement>(null);
  const lang = className?.replace(/^hljs\s+/, '').replace('language-', '') || '';
  const { t } = useTranslation('chat');

  const handleCopy = useCallback(() => {
    // 从 DOM 提取纯文本而非从 React children，保证 hljs 嵌套也能拿到正确内容
    const text = codeRef.current?.textContent ?? extractText(children);
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [children]);

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{lang || 'code'}</span>
        <button
          type="button"
          className={`code-block-copy ${copied ? 'copied' : ''}`}
          onClick={handleCopy}
          aria-label={t('copyCode')}
        >
          {copied ? t('copied') : t('copyCode')}
        </button>
      </div>
      <pre>
        <code ref={codeRef} className={className}>
          {children}
        </code>
      </pre>
    </div>
  );
}
