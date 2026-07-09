import type { ReactNode } from 'react';
import { Card, type CardProps } from 'antd';

interface Props extends CardProps {
  table?: boolean;
  title?: ReactNode;
}

export function PageCard({ table, className, variant = 'borderless', ...props }: Props) {
  const classes = ['page-card', table ? 'page-table-card' : '', className].filter(Boolean).join(' ');
  return <Card variant={variant} className={classes} {...props} />;
}

export function PageCardIcon({
  color,
  bg,
  children,
}: {
  color: string;
  bg: string;
  children: ReactNode;
}) {
  return (
    <span className="page-card__icon" style={{ color, background: bg }}>
      {children}
    </span>
  );
}

export function PageCardTitle({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <span className="page-card__title">
      {icon}
      {children}
    </span>
  );
}

export function PageInfoItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="page-info-item__label">{label}</div>
      <div className="page-info-item__value">{value}</div>
    </div>
  );
}
