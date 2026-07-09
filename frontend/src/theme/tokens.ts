import type { ThemeConfig } from 'antd';
import { theme as antdTheme } from 'antd';

// ── JS 侧色值引用（与 tokens.css 同名变量保持一致）─────────

export const PALETTE = {
  neutral: {
    n0: '#1C2636',
    n1: '#253548',
    n2: '#3A506B',
    n3: '#526881',
    n4: '#71869C',
    n5: '#93A4B5',
    n6: '#B3C0CD',
    n7: '#D6DCE4',
    n8: '#E8ECF1',
    n9: '#F3F5F8',
    n10: '#FBFCFD',
  },
  accent: '#5BC0BE',
  warning: '#C9A68B',
  info: '#A8B59F',
  highlight: '#CDEDF6',
  error: '#C96B6B',
} as const;

export function rgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── 按钮/强调渐变（仅用于显式强调场景，不用于结构面）───────

export const GRADIENTS = {
  /** 主按钮：深灰蓝 → 柔青绿 */
  primaryBtn: `linear-gradient(135deg, ${PALETTE.neutral.n2} 0%, ${PALETTE.accent} 100%)`,
  /** 品牌文字 */
  brandText: `linear-gradient(135deg, ${PALETTE.neutral.n2} 0%, ${PALETTE.accent} 50%, ${PALETTE.info} 100%)`,
  /** PageCardIcon 渐变 */
  pageIcon: {
    blue: `linear-gradient(135deg, ${PALETTE.neutral.n2} 0%, ${PALETTE.accent} 100%)`,
    green: `linear-gradient(135deg, ${PALETTE.info} 0%, ${PALETTE.accent} 100%)`,
    warm: `linear-gradient(135deg, ${PALETTE.warning} 0%, ${PALETTE.neutral.n2} 100%)`,
  },
} as const;

// ── Ant Design ConfigProvider 配置 ──────────────────────────
// 关键：中性色主导 token，语义色仅映射到 Ant Design 语义 token

export function createAntdThemeConfig(dark: boolean): ThemeConfig {
  const n = PALETTE.neutral;

  return {
    algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,

    token: {
      // 语义映射：柔青绿 → success / 陶土 → warning / 鼠尾草 → info
      colorPrimary: n.n2,
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

      // 边框
      colorBorder: dark ? 'rgba(255,255,255,0.08)' : n.n6,
      colorBorderSecondary: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)',

      // 文字 — 必须用显式 hex，CSS var 会导致 Ant Design 无法计算派生色
      colorText: dark ? '#E4E8EE' : n.n0,
      colorTextSecondary: dark ? '#93A4B5' : n.n3,
      colorTextTertiary: dark ? '#71869C' : n.n4,
      colorTextQuaternary: dark ? '#526881' : n.n5,
    },

    components: {
      Layout: {
        headerBg: dark ? n.n0 : n.n10,
        // 侧栏更深 → 退后；内容区更亮 → 聚焦
        siderBg: dark ? n.n0 : n.n7,
        bodyBg: dark ? n.n0 : n.n9,
      },
      Menu: {
        itemBorderRadius: 8,
        itemMarginInline: 8,
        itemHeight: 38,
        iconSize: 17,
        // 选中颜色用柔青绿——晶脉透光
        itemSelectedColor: PALETTE.accent,
        itemColor: dark ? 'rgba(255,255,255,0.55)' : n.n3,
        itemHoverColor: dark ? 'rgba(255,255,255,0.85)' : n.n2,
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
        activeShadow: `0 0 0 2px ${rgba(PALETTE.accent, 0.15)}`,
      },
      Table: {
        borderRadiusLG: 10,
        headerBg: dark ? n.n1 : n.n10,
        headerBorderRadius: 10,
        rowHoverBg: dark ? 'rgba(255,255,255,0.04)' : rgba(PALETTE.accent, 0.08),
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
