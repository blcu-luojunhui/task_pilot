import { PALETTE, rgba } from '@/theme/tokens';

/** 页面级 CSS 变量 */
export function usePageStyleVars(): React.CSSProperties {
  return {
    '--page-border': 'var(--border-default)',
    '--page-shadow': 'var(--shadow-elevated)',
    '--page-hero-bg': rgba(PALETTE.neutral.n6, 0.25),
    '--page-row-hover': rgba(PALETTE.neutral.n2, 0.04),
  } as React.CSSProperties;
}

/** PageHero avatar 背景 — 纯色，不用渐变 */
export const PAGE_GRADIENTS = {
  blue:   PALETTE.neutral.n0,
  green:  PALETTE.neutral.n3,
  orange: PALETTE.warning,
  purple: PALETTE.neutral.n2,
  cyan:   PALETTE.neutral.n4,
  indigo: PALETTE.neutral.n1,
} as const;
