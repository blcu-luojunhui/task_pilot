import type { ReactNode } from 'react';
import { usePageStyleVars } from '@/hooks/usePageStyleVars';
import './PageLayout.css';

interface Props {
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export function PageShell({ children, className, style }: Props) {
  const vars = usePageStyleVars();
  const classes = ['page-shell', className].filter(Boolean).join(' ');
  return (
    <div className={classes} style={{ ...vars, ...style }}>
      {children}
    </div>
  );
}
