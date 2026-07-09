/** 用户可调的全局语义色板（映射到 tokens.css / Ant Design） */
export interface ThemePalette {
  /** 主色：正文、按钮、导航选中 */
  primary: string;
  /** 强调色：链接、标签、选中态 */
  accent: string;
  /** 页面背景 */
  pageBg: string;
  /** 侧栏 / 卡片背景 */
  cardBg: string;
  /** 浮层 / Header 背景 */
  elevatedBg: string;
  /** 边框色 */
  border: string;
}

/** 主色固定为黑，不参与主题染色 */
export const THEME_INK = '#1A1A1A';

function parseHex(hex: string): [number, number, number] | null {
  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) return null;
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  if ([r, g, b].some((v) => Number.isNaN(v))) return null;
  return [r, g, b];
}

/** 与白色混合 — 用于淡色背景 */
function mixWithWhite(hex: string, whiteRatio: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return hex;
  const t = Math.min(1, Math.max(0, whiteRatio));
  const mix = (c: number) => Math.round(c + (255 - c) * t);
  const toHex = (n: number) => n.toString(16).padStart(2, '0');
  return `#${toHex(mix(rgb[0]))}${toHex(mix(rgb[1]))}${toHex(mix(rgb[2]))}`;
}

function mixHex(a: string, b: string, t: number): string {
  const c1 = parseHex(a);
  const c2 = parseHex(b);
  if (!c1 || !c2) return a;
  const mix = (i: number) => Math.round(c1[i] + (c2[i] - c1[i]) * t);
  const toHex = (n: number) => n.toString(16).padStart(2, '0');
  return `#${toHex(mix(0))}${toHex(mix(1))}${toHex(mix(2))}`;
}

/** 青橙山光 — 默认主题 */
export const DEFAULT_THEME_PALETTE: ThemePalette = {
  primary: THEME_INK,
  accent: '#e4701f',
  pageBg: mixWithWhite('#a2b8b8', 0.84),
  cardBg: mixWithWhite('#696d69', 0.7),
  elevatedBg: mixWithWhite('#a2b8b8', 0.92),
  border: mixWithWhite('#e4701f', 0.78),
};

export interface ThemeSurfaceGradients {
  page: string;
  card: string;
  elevated: string;
  header: string;
}

function linearGradient(from: string, to: string, angle = 165): string {
  return `linear-gradient(${angle}deg, ${from} 0%, ${to} 100%)`;
}

/** 由调色板基色 + 强调色推导淡色表面渐变（全主题通用） */
export function buildSurfaceGradients(palette: ThemePalette): ThemeSurfaceGradients {
  const { pageBg, cardBg, elevatedBg, accent } = palette;
  const accentWash = mixWithWhite(accent, 0.88);

  const pageTop = mixWithWhite(pageBg, 0.42);
  const pageBottom = mixHex(pageBg, accentWash, 0.18);

  const cardTop = mixWithWhite(cardBg, 0.22);
  const cardBottom = mixHex(cardBg, accentWash, 0.2);

  const elevatedTop = mixWithWhite(elevatedBg, 0.38);
  const elevatedBottom = mixHex(elevatedBg, pageBg, 0.35);

  const headerTop = mixWithWhite(elevatedBg, 0.52);
  const headerBottom = mixWithWhite(pageBg, 0.28);

  return {
    page: linearGradient(pageTop, pageBottom, 165),
    card: linearGradient(cardTop, cardBottom, 180),
    elevated: linearGradient(elevatedTop, elevatedBottom, 180),
    header: linearGradient(headerTop, headerBottom, 180),
  };
}

export const THEME_PALETTE_PRESETS: Record<string, ThemePalette> = {
  default: DEFAULT_THEME_PALETTE,
  warm: {
    primary: THEME_INK,
    accent: '#8B6914',
    pageBg: '#FAF8F5',
    cardBg: '#EDE8E0',
    elevatedBg: '#FFFCF7',
    border: '#D9D2C5',
  },
  cool: {
    primary: THEME_INK,
    accent: '#2563EB',
    pageBg: '#F4F6F8',
    cardBg: '#E2E8EF',
    elevatedBg: '#FAFBFC',
    border: '#CBD5E1',
  },
  /**
   * 暖金雾岭 — 四色源：
   * 雾金 #e1ca9e · 雾岭 #adb093 · 暖金 #998560 · 岭褐 #3e3425
   * 页面/侧栏用源色高比例兑白作淡底，主色固定黑，暖金作强调。
   */
  warmGoldMist: {
    primary: THEME_INK,
    accent: '#998560',
    pageBg: mixWithWhite('#e1ca9e', 0.86),
    cardBg: mixWithWhite('#adb093', 0.72),
    elevatedBg: mixWithWhite('#e1ca9e', 0.93),
    border: mixWithWhite('#998560', 0.78),
  },
  /**
   * 灰调海浪 — 四色源：
   * 雾灰 #e6dede · 石灰 #bab4b3 · 海雾 #6f919d · 深海 #42717e
   * 页面/侧栏用源色高比例兑白作淡底，主色固定黑，海雾作强调。
   */
  grayOcean: {
    primary: THEME_INK,
    accent: '#6f919d',
    pageBg: mixWithWhite('#e6dede', 0.84),
    cardBg: mixWithWhite('#bab4b3', 0.7),
    elevatedBg: mixWithWhite('#e6dede', 0.92),
    border: mixWithWhite('#6f919d', 0.76),
  },
  /**
   * 星垂平野 — 四色源：
   * 天青 #c6d0d4 · 野灰 #737b7b · 野绿 #383f0f · 夜野 #21220a
   * 页面/侧栏用源色高比例兑白作淡底，主色固定黑，野绿作强调。
   */
  starPlain: {
    primary: THEME_INK,
    accent: '#383f0f',
    pageBg: mixWithWhite('#c6d0d4', 0.84),
    cardBg: mixWithWhite('#737b7b', 0.7),
    elevatedBg: mixWithWhite('#c6d0d4', 0.92),
    border: mixWithWhite('#383f0f', 0.78),
  },
  /**
   * 青橙山光 — 四色源：
   * 山青 #a2b8b8 · 山橙 #e4701f · 山灰 #696d69 · 深山 #1e2d2c
   */
  cyanOrangeMountain: { ...DEFAULT_THEME_PALETTE },
};

export function rgba(hex: string, alpha: number): string {
  const rgb = parseHex(hex);
  if (!rgb) return `rgba(0,0,0,${alpha})`;
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`;
}

/** 将调色板写入 document 根 CSS 变量 */
export function applyPaletteToDocument(palette: ThemePalette): void {
  const root = document.documentElement;
  const ink = THEME_INK;
  const n2 = mixHex(ink, palette.accent, 0.25);
  const n3 = mixWithWhite(ink, 0.28);
  const n4 = mixWithWhite(ink, 0.48);
  const n5 = mixWithWhite(ink, 0.62);
  const n8 = mixHex(palette.cardBg, palette.elevatedBg, 0.45);
  const gradients = buildSurfaceGradients(palette);

  const vars: Record<string, string> = {
    '--n0': ink,
    '--n2': n2,
    '--n3': n3,
    '--n4': n4,
    '--n5': n5,
    '--n6': palette.border,
    '--n7': palette.cardBg,
    '--n8': n8,
    '--n9': palette.pageBg,
    '--n10': palette.elevatedBg,
    '--color-primary': ink,
    '--color-primary-soft': rgba(ink, 0.06),
    '--color-accent': palette.accent,
    '--color-accent-soft': rgba(palette.accent, 0.08),
    '--text-primary': ink,
    '--text-secondary': n3,
    '--text-tertiary': n4,
    '--text-disabled': n5,
    '--surface-page': gradients.page,
    '--surface-card': gradients.card,
    '--surface-elevated': gradients.elevated,
    '--surface-header': gradients.header,
    '--border-default': rgba(ink, 0.06),
    '--border-light': rgba(ink, 0.03),
  };

  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value);
  }
}

export function clearPaletteOverrides(): void {
  const keys = [
    '--n0', '--n2', '--n3', '--n4', '--n5', '--n6', '--n7', '--n8', '--n9', '--n10',
    '--color-primary', '--color-primary-soft', '--color-accent', '--color-accent-soft',
    '--text-primary', '--text-secondary', '--text-tertiary', '--text-disabled',
    '--surface-page', '--surface-card', '--surface-elevated', '--surface-header',
    '--border-default', '--border-light',
  ];
  for (const key of keys) {
    document.documentElement.style.removeProperty(key);
  }
}

/** 主题预设展示名（i18n key 后缀） */
export const THEME_PRESET_ORDER = [
  'default',
  'warmGoldMist',
  'grayOcean',
  'starPlain',
  'warm',
  'cool',
] as const;

export type ThemePresetId = (typeof THEME_PRESET_ORDER)[number];

/** 暖金雾岭四色源（展示用） */
export const WARM_GOLD_MIST_SWATCHES = [
  { hex: '#e1ca9e', key: 'mistGold' },
  { hex: '#adb093', key: 'mistRidge' },
  { hex: '#998560', key: 'warmGold' },
  { hex: '#3e3425', key: 'ridgeBrown' },
] as const;

/** 灰调海浪四色源（展示用） */
export const GRAY_OCEAN_SWATCHES = [
  { hex: '#e6dede', key: 'mistGray' },
  { hex: '#bab4b3', key: 'stoneGray' },
  { hex: '#6f919d', key: 'seaMist' },
  { hex: '#42717e', key: 'deepOcean' },
] as const;

/** 星垂平野四色源（展示用） */
export const STAR_PLAIN_SWATCHES = [
  { hex: '#c6d0d4', key: 'skyMist' },
  { hex: '#737b7b', key: 'fieldGray' },
  { hex: '#383f0f', key: 'fieldGreen' },
  { hex: '#21220a', key: 'nightField' },
] as const;

/** 青橙山光四色源（展示用） */
export const CYAN_ORANGE_MOUNTAIN_SWATCHES = [
  { hex: '#a2b8b8', key: 'mountainCyan' },
  { hex: '#e4701f', key: 'mountainOrange' },
  { hex: '#696d69', key: 'mountainGray' },
  { hex: '#1e2d2c', key: 'deepMountain' },
] as const;

export function normalizePalette(input: Partial<ThemePalette> | null | undefined): ThemePalette {
  return { ...DEFAULT_THEME_PALETTE, ...input, primary: THEME_INK };
}
