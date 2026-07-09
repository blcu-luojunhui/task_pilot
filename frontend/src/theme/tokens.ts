import type { ThemeConfig } from 'antd';
import { theme as antdTheme } from 'antd';

// ── JS 侧色值引用（与 tokens.css 同名变量保持一致）─────────
// Muji / Notion 极简留白：暖灰中性色阶 + 克制语义色

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

// ── 纯色引用（渐变已废弃，Muji/Notion 极简风格）───────────

export const SOLIDS = {
  /** 主按钮 */
  primaryBtn: PALETTE.neutral.n0,
  /** 品牌文字 */
  brandText: PALETTE.neutral.n0,
  /** PageCardIcon 纯色 */
  pageIcon: {
    blue: PALETTE.neutral.n2,
    green: PALETTE.neutral.n4,
    warm: PALETTE.warning,
  },
} as const;

// ── Ant Design ConfigProvider 配置 ──────────────────────────
// 关键：中性色主导 token，语义色仅映射到 Ant Design 语义 token

export function createAntdThemeConfig(dark: boolean): ThemeConfig {
  const n = PALETTE.neutral;

  return {
    algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,

    token: {
      // 语义映射
      colorPrimary: n.n0,        // 纯黑 primary — 极简克制
      colorSuccess: PALETTE.accent,
      colorWarning: PALETTE.warning,
      colorInfo: PALETTE.info,
      colorError: PALETTE.error,

      // 排版
      fontFamily: "var(--font-sans)",
      fontFamilyCode: "var(--font-mono)",
      fontSize: 14,
      lineHeight: 1.6,
      borderRadius: 8,
      controlHeight: 36,
      paddingContentHorizontal: 20,
      paddingContentVertical: 16,

      // 边框 — 暖灰，极淡
      colorBorder: dark ? 'rgba(255,255,255,0.08)' : n.n6,
      colorBorderSecondary: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)',

      // 文字 — 暖灰阶，不用蓝黑
      colorText: dark ? '#E5E5E5' : n.n0,
      colorTextSecondary: dark ? '#A3A3A3' : n.n3,
      colorTextTertiary: dark ? '#737373' : n.n4,
      colorTextQuaternary: dark ? '#525252' : n.n5,
    },

    components: {
      Layout: {
        headerBg: dark ? n.n0 : n.n10,
        siderBg: dark ? n.n0 : n.n7,
        bodyBg: dark ? n.n0 : n.n9,
      },
      Menu: {
        itemBorderRadius: 8,
        itemMarginInline: 8,
        itemHeight: 38,
        iconSize: 17,
        itemSelectedColor: PALETTE.accent,
        itemColor: dark ? 'rgba(255,255,255,0.55)' : n.n3,
        itemHoverColor: dark ? 'rgba(255,255,255,0.85)' : n.n0,
      },
      Card: {
        borderRadiusLG: 10,
        paddingLG: 20,
      },
      Button: {
        borderRadius: 8,
        controlHeight: 36,
        paddingInline: 16,
        contentFontSize: 14,
      },
      Input: {
        borderRadius: 8,
        controlHeight: 36,
        activeBorderColor: PALETTE.accent,
        activeShadow: `0 0 0 2px ${rgba(PALETTE.accent, 0.1)}`,
      },
      Table: {
        borderRadiusLG: 10,
        headerBg: dark ? n.n1 : n.n10,
        headerBorderRadius: 10,
        rowHoverBg: dark ? 'rgba(255,255,255,0.04)' : rgba(PALETTE.accent, 0.04),
      },
      Segmented: { borderRadius: 8 },
      Select: { borderRadius: 8 },
      DatePicker: { borderRadius: 8 },
      Tag: { borderRadiusSM: 4 },
      Tabs: {
        itemActiveColor: PALETTE.accent,
        itemHoverColor: PALETTE.accent,
        inkBarColor: PALETTE.accent,
      },
    },
  };
}
