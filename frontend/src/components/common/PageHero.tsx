import type { ReactNode } from 'react';
import { Typography } from 'antd';
import { PAGE_GRADIENTS } from '@/hooks/usePageStyleVars';

interface Props {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  avatarText?: string;
  gradient?: keyof typeof PAGE_GRADIENTS;
  extra?: ReactNode;
}

export function PageHero({
  title,
  subtitle,
  icon,
  avatarText,
  gradient = 'blue',
  extra,
}: Props) {
  const avatarContent = icon ?? avatarText?.slice(0, 1).toUpperCase() ?? '?';

  return (
    <header className="page-hero">
      <div
        className="page-hero__avatar"
        style={{ background: PAGE_GRADIENTS[gradient] }}
      >
        {avatarContent}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Typography.Title level={2} className="page-hero__title">
          {title}
        </Typography.Title>
        {subtitle && (
          <Typography.Text type="secondary" className="page-hero__subtitle">
            {subtitle}
          </Typography.Text>
        )}
      </div>
      {extra}
    </header>
  );
}
