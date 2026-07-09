import type { ThemeConfig } from 'antd';
import { theme as antdTheme } from 'antd';
import {
  DEFAULT_THEME_PALETTE,
  rgba,
  THEME_INK,
  type ThemePalette,
} from '@/theme/palette';

// ── JS 侧色值引用（与 tokens.css / palette 保持一致）─────────

export const PALETTE = {
  neutral: {
    n0: DEFAULT_THEME_PALETTE.primary,
    n1: '#262626',
    n2: '#404040',
    n3: '#525252',
    n4: '#737373',
    n5: '#A3A3A3',
    n6: DEFAULT_THEME_PALETTE.border,
    n7: DEFAULT_THEME_PALETTE.cardBg,
    n8: '#F0F0EE',
    n9: DEFAULT_THEME_PALETTE.pageBg,
    n10: DEFAULT_THEME_PALETTE.elevatedBg,
  },
  accent: DEFAULT_THEME_PALETTE.accent,
  warning: '#B45309',
  info: '#525252',
  highlight: '#FEF3C7',
  error: '#B91C1C',
} as const;

export { rgba };

// ── 纯色引用（渐变已废弃）──────────────────────────────────

export const SOLIDS = {
  primaryBtn: PALETTE.neutral.n0,
  brandText: PALETTE.neutral.n0,
  pageIcon: {
    blue: PALETTE.neutral.n2,
    green: PALETTE.neutral.n4,
    warm: PALETTE.warning,
  },
} as const;

// ── Ant Design ConfigProvider 配置 ──────────────────────────

export function createAntdThemeConfig(
  dark: boolean,
  palette: ThemePalette = DEFAULT_THEME_PALETTE,
): ThemeConfig {
  const p = { ...palette, primary: THEME_INK };
  const ink = THEME_INK;

  return {
    algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,

    token: {
      colorPrimary: ink,
      colorSuccess: p.accent,
      colorWarning: PALETTE.warning,
      colorInfo: PALETTE.info,
      colorError: PALETTE.error,

      fontFamily: 'var(--font-sans)',
      fontFamilyCode: 'var(--font-mono)',
      fontSize: 14,
      lineHeight: 1.5,
      borderRadius: 6,
      controlHeight: 36,
      paddingContentHorizontal: 16,
      paddingContentVertical: 12,

      colorBorder: dark ? 'rgba(255,255,255,0.08)' : p.border,
      colorBorderSecondary: dark ? 'rgba(255,255,255,0.05)' : rgba(ink, 0.04),

      colorText: dark ? '#E5E5E5' : ink,
      colorTextSecondary: dark ? '#A3A3A3' : rgba(ink, 0.72),
      colorTextTertiary: dark ? '#737373' : rgba(ink, 0.55),
      colorTextQuaternary: dark ? '#525252' : rgba(ink, 0.42),

      colorBgLayout: p.pageBg,
      colorBgContainer: p.elevatedBg,
      colorBgElevated: p.elevatedBg,

      boxShadow: 'none',
      boxShadowSecondary: 'none',
    },

    components: {
      Layout: {
        headerBg: 'transparent',
        siderBg: 'transparent',
        bodyBg: p.elevatedBg,
      },
      Menu: {
        itemBorderRadius: 0,
        itemMarginInline: 0,
        itemHeight: 40,
        iconSize: 16,
        itemSelectedColor: ink,
        itemColor: rgba(ink, 0.55),
        itemHoverColor: ink,
        itemSelectedBg: 'transparent',
        itemBg: 'transparent',
        subMenuItemBg: 'transparent',
      },
      Card: {
        borderRadiusLG: 8,
        paddingLG: 16,
        boxShadow: 'none',
      },
      Button: {
        borderRadius: 6,
        controlHeight: 36,
        paddingInline: 14,
        contentFontSize: 14,
        boxShadow: 'none',
      },
      Input: {
        borderRadius: 6,
        controlHeight: 36,
        activeBorderColor: ink,
        activeShadow: 'none',
      },
      Table: {
        borderRadiusLG: 0,
        headerBg: 'transparent',
        headerBorderRadius: 0,
        rowHoverBg: rgba(ink, 0.02),
        boxShadow: 'none',
      },
      Tag: { borderRadiusSM: 4 },
      Tabs: {
        itemActiveColor: ink,
        itemHoverColor: rgba(ink, 0.72),
        inkBarColor: ink,
      },
    },
  };
}
