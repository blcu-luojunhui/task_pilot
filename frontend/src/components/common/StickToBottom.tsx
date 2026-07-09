import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from 'antd';
import { VerticalAlignBottomOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const BOTTOM_THRESHOLD = 80;

interface Props {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
  /** 内容变化时触发（消息数、工具调用数等） */
  deps?: unknown[];
}

/**
 * 智能滚动容器（FE-5）：仅当用户已在底部时自动跟随新内容；
 * 否则显示「回到底部」悬浮按钮。
 */
export function StickToBottom({ children, className, style, deps = [] }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const { t } = useTranslation('chat');

  const checkAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
    setAtBottom(true);
  }, []);

  const handleScroll = useCallback(() => {
    setAtBottom(checkAtBottom());
  }, [checkAtBottom]);

  useEffect(() => {
    if (atBottom) {
      scrollToBottom('auto');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return (
    <div style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div
        ref={containerRef}
        className={className}
        style={{ flex: 1, overflowY: 'auto', minHeight: 0, ...style }}
        onScroll={handleScroll}
      >
        {children}
      </div>
      {!atBottom && (
        <Button
          type="primary"
          size="small"
          icon={<VerticalAlignBottomOutlined />}
          onClick={() => scrollToBottom('smooth')}
          style={{
            position: 'absolute',
            bottom: 16,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
            boxShadow: 'none',
          }}
        >
          {t('scrollToBottom')}
        </Button>
      )}
    </div>
  );
}
