import { THEME_INK } from '@/theme/palette';
import { useThemePaletteStore } from '@/stores/themePaletteStore';

export type IconTone = 'accent' | 'warning' | 'neutral';

export type IconToneStyle = { color: string; bg: string };

export function useIconTones(): Record<IconTone, IconToneStyle> {
  const palette = useThemePaletteStore((s) => s.palette);
  return {
    accent: { color: '#fff', bg: THEME_INK },
    warning: { color: '#fff', bg: palette.accent },
    neutral: { color: '#fff', bg: 'var(--n2)' },
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
