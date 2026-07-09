import type { ThemeConfig } from 'antd';
import { theme as antdTheme } from 'antd';

// ── JS 侧色值引用（与 tokens.css 同名变量保持一致）─────────
// Muji / Notion 极简留白：暖灰中性色阶 + 纯黑强调

export const PALETTE = {
  neutral: {
    n0: '#171717',
    n1: '#262626',
    n2: '#404040',
    n3: '#525252',
    n4: '#737373',
    n5: '#A3A3A3',
    n6: '#D4D4D4',
    n7: '#E5E5E5',
    n8: '#F0F0EE',
    n9: '#F5F5F4',
    n10: '#FAFAF9',
  },
  accent: '#1A1A1A',
  warning: '#B45309',
  info: '#525252',
  highlight: '#FEF3C7',
  error: '#B91C1C',
} as const;

export function rgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

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
// 去装饰：无阴影、无渐变、无背景色填充

export function createAntdThemeConfig(dark: boolean): ThemeConfig {
  const n = PALETTE.neutral;

  return {
    algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,

    token: {
      colorPrimary: n.n0,
      colorSuccess: PALETTE.accent,
      colorWarning: PALETTE.warning,
      colorInfo: PALETTE.info,
      colorError: PALETTE.error,

      fontFamily: "var(--font-sans)",
      fontFamilyCode: "var(--font-mono)",
      fontSize: 14,
      lineHeight: 1.5,
      borderRadius: 6,
      controlHeight: 36,
      paddingContentHorizontal: 16,
      paddingContentVertical: 12,

      colorBorder: dark ? 'rgba(255,255,255,0.08)' : n.n6,
      colorBorderSecondary: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)',

      colorText: dark ? '#E5E5E5' : n.n0,
      colorTextSecondary: dark ? '#A3A3A3' : n.n3,
      colorTextTertiary: dark ? '#737373' : n.n4,
      colorTextQuaternary: dark ? '#525252' : n.n5,

      // 去装饰
      boxShadow: 'none',
      boxShadowSecondary: 'none',
    },

    components: {
      Layout: {
        headerBg: 'transparent',
        siderBg: 'transparent',
        bodyBg: '#FFFFFF',
      },
      Menu: {
        itemBorderRadius: 0,
        itemMarginInline: 0,
        itemHeight: 40,
        iconSize: 16,
        itemSelectedColor: n.n0,
        itemColor: n.n4,
        itemHoverColor: n.n0,
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
        activeBorderColor: n.n0,
        activeShadow: 'none',
      },
      Table: {
        borderRadiusLG: 0,
        headerBg: 'transparent',
        headerBorderRadius: 0,
        rowHoverBg: 'rgba(0,0,0,0.02)',
        boxShadow: 'none',
      },
      Tag: { borderRadiusSM: 4 },
      Tabs: {
        itemActiveColor: n.n0,
        itemHoverColor: n.n3,
        inkBarColor: n.n0,
      },
    },
  };
}
