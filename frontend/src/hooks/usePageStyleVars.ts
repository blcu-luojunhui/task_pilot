import { useDarkMode } from '@/hooks/useDarkMode';

/** Account 风格页面 CSS 变量（亮/暗主题） */
export function usePageStyleVars(): React.CSSProperties {
  const [dark] = useDarkMode();
  return {
    '--page-border': dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)',
    '--page-shadow': dark ? '0 2px 16px rgba(0,0,0,0.35)' : '0 2px 16px rgba(0,0,0,0.04)',
    '--page-hero-bg': dark
      ? 'linear-gradient(135deg, rgba(0,122,255,0.12) 0%, rgba(88,86,214,0.08) 100%)'
      : 'linear-gradient(135deg, rgba(0,122,255,0.06) 0%, rgba(88,86,214,0.04) 100%)',
    '--page-row-hover': dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,122,255,0.03)',
  } as React.CSSProperties;
}

export const PAGE_GRADIENTS = {
  blue: 'linear-gradient(135deg, #007aff 0%, #5856d6 100%)',
  green: 'linear-gradient(135deg, #34c759 0%, #30b0c7 100%)',
  orange: 'linear-gradient(135deg, #ff9500 0%, #ff2d55 100%)',
  purple: 'linear-gradient(135deg, #5856d6 0%, #af52de 100%)',
  cyan: 'linear-gradient(135deg, #32ade6 0%, #007aff 100%)',
  indigo: 'linear-gradient(135deg, #5e5ce6 0%, #007aff 100%)',
} as const;
