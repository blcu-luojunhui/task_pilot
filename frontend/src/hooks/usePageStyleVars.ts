import { PALETTE, rgba } from '@/theme/tokens';
import { useThemePaletteStore } from '@/stores/themePaletteStore';

/** 页面级 CSS 变量 */
export function usePageStyleVars(): React.CSSProperties {
  const palette = useThemePaletteStore((s) => s.palette);
  return {
    '--page-border': 'var(--border-default)',
    '--page-shadow': 'none',
    '--page-hero-bg': rgba(palette.border, 0.25),
    '--page-row-hover': rgba(palette.primary, 0.04),
  } as React.CSSProperties;
}

/** @deprecated 使用 PageHeroGradient / usePageHeroIconTone */
export const PAGE_GRADIENTS = {
  blue: PALETTE.neutral.n2,
  green: PALETTE.neutral.n4,
  orange: PALETTE.warning,
  purple: PALETTE.neutral.n2,
  cyan: PALETTE.neutral.n4,
  indigo: PALETTE.neutral.n1,
} as const;
