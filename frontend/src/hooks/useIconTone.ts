import { PALETTE, rgba } from '@/theme/tokens';
import { useThemePaletteStore } from '@/stores/themePaletteStore';

export type IconTone = 'accent' | 'warning' | 'neutral';

export type IconToneStyle = { color: string; bg: string };

export function useIconTones(): Record<IconTone, IconToneStyle> {
  const palette = useThemePaletteStore((s) => s.palette);
  return {
    accent: { color: palette.accent, bg: rgba(palette.accent, 0.1) },
    warning: { color: PALETTE.warning, bg: rgba(PALETTE.warning, 0.1) },
    neutral: { color: 'var(--n2)', bg: rgba(palette.accent, 0.06) },
  };
}

export const PAGE_HERO_GRADIENTS = [
  'blue',
  'green',
  'orange',
  'purple',
  'cyan',
  'indigo',
] as const;

export type PageHeroGradient = (typeof PAGE_HERO_GRADIENTS)[number];

export function usePageHeroIconTone(gradient: PageHeroGradient): IconToneStyle {
  const tones = useIconTones();
  return gradient === 'orange' ? tones.warning : tones.accent;
}
