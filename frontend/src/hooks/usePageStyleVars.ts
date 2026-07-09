import { PALETTE, rgba } from '@/theme/tokens';

/** 页面级 CSS 变量 */
export function usePageStyleVars(): React.CSSProperties {
  return {
    '--page-border': 'var(--border-default)',
    '--page-shadow': 'var(--shadow-elevated)',
    '--page-hero-bg': `linear-gradient(135deg, ${rgba(PALETTE.neutral.n2, 0.08)} 0%, ${rgba(PALETTE.accent, 0.04)} 100%)`,
    '--page-row-hover': rgba(PALETTE.neutral.n2, 0.04),
  } as React.CSSProperties;
}

export const PAGE_GRADIENTS = {
  blue:   'linear-gradient(135deg, var(--n2) 0%, var(--color-accent) 100%)',
  green:  'linear-gradient(135deg, var(--color-info) 0%, var(--color-accent) 100%)',
  orange: 'linear-gradient(135deg, var(--color-warning) 0%, var(--n2) 100%)',
  purple: 'linear-gradient(135deg, var(--n2) 0%, var(--color-warning) 100%)',
  cyan:   'linear-gradient(135deg, var(--n2) 0%, var(--color-highlight) 100%)',
  indigo: 'linear-gradient(135deg, var(--n2) 0%, var(--color-info) 100%)',
} as const;
