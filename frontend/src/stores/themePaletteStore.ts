import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  DEFAULT_THEME_PALETTE,
  THEME_INK,
  THEME_PALETTE_PRESETS,
  applyPaletteToDocument,
  normalizePalette,
  type ThemePalette,
  type ThemePresetId,
} from '@/theme/palette';

interface ThemePaletteState {
  palette: ThemePalette;
  setColor: (key: keyof ThemePalette, value: string) => void;
  applyPreset: (presetId: ThemePresetId) => void;
  reset: () => void;
}

export const useThemePaletteStore = create<ThemePaletteState>()(
  persist(
    (set, get) => ({
      palette: DEFAULT_THEME_PALETTE,

      setColor: (key, value) => {
        const next = { ...get().palette, [key]: value, primary: THEME_INK };
        set({ palette: next });
        applyPaletteToDocument(next);
      },

      applyPreset: (presetId) => {
        const preset = THEME_PALETTE_PRESETS[presetId] ?? DEFAULT_THEME_PALETTE;
        const next = { ...preset, primary: THEME_INK };
        set({ palette: next });
        applyPaletteToDocument(next);
      },

      reset: () => {
        set({ palette: DEFAULT_THEME_PALETTE });
        applyPaletteToDocument(DEFAULT_THEME_PALETTE);
      },
    }),
    {
      name: 'taskpilot-theme-palette',
      merge: (persisted, current) => ({
        ...current,
        palette: normalizePalette(
          (persisted as Partial<ThemePaletteState> | undefined)?.palette,
        ),
      }),
      onRehydrateStorage: () => (state) => {
        if (state?.palette) {
          applyPaletteToDocument(state.palette);
        }
      },
    },
  ),
);

/** 启动时同步 CSS 变量（含 SSR 之外的首次渲染） */
export function syncThemePaletteFromStore(): void {
  applyPaletteToDocument(useThemePaletteStore.getState().palette);
}
