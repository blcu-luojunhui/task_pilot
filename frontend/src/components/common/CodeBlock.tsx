import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  className?: string;
  children: React.ReactNode;
}

/** 带语言标签与复制按钮的代码块（FE-5） */
export function CodeBlock({ className, children }: Props) {
  const [copied, setCopied] = useState(false);
  const lang = className?.replace('language-', '') || '';
  const codeStr = String(children).replace(/\n$/, '');
  const { t } = useTranslation('chat');

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(codeStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [codeStr]);

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
        <code className={className}>{codeStr}</code>
      </pre>
    </div>
  );
}
