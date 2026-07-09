import type { ReactNode } from 'react';
import { Typography } from 'antd';
import { PAGE_GRADIENTS } from '@/hooks/usePageStyleVars';
import { usePageHeroIconTone, type PageHeroGradient } from '@/hooks/useIconTone';

interface Props {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  avatarText?: string;
  avatarSrc?: string;
  gradient?: PageHeroGradient | keyof typeof PAGE_GRADIENTS;
  extra?: ReactNode;
}

export function PageHero({
  title,
  subtitle,
  icon,
  avatarText,
  avatarSrc,
  gradient = 'blue',
  extra,
}: Props) {
  const tone = usePageHeroIconTone(gradient as PageHeroGradient);

  const avatarContent = avatarSrc ? (
    <img
      src={avatarSrc}
      alt=""
      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
    />
  ) : icon ? (
    <span className="page-hero__icon">{icon}</span>
  ) : (
    avatarText?.slice(0, 1).toUpperCase() ?? '?'
  );

  const avatarStyle = avatarSrc
    ? { background: '#fff', overflow: 'hidden' as const }
    : {
        background: tone.bg,
        color: icon ? tone.color : 'var(--n0)',
      };

  return (
    <header className="page-hero">
      <div className="page-hero__avatar" style={avatarStyle}>
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
