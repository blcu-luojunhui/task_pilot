import { Button, Select, Space, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { useThemePaletteStore } from '@/stores/themePaletteStore';
import {
  CYAN_ORANGE_MOUNTAIN_SWATCHES,
  DEFAULT_THEME_PALETTE,
  GRAY_OCEAN_SWATCHES,
  STAR_PLAIN_SWATCHES,
  THEME_PALETTE_PRESETS,
  THEME_PRESET_ORDER,
  WARM_GOLD_MIST_SWATCHES,
  buildSurfaceGradients,
  type ThemePalette,
  type ThemePresetId,
} from '@/theme/palette';

const PALETTE_FIELDS: Array<{ key: keyof ThemePalette; labelKey: string }> = [
  { key: 'accent', labelKey: 'themeAccent' },
  { key: 'pageBg', labelKey: 'themePageBg' },
  { key: 'cardBg', labelKey: 'themeCardBg' },
  { key: 'elevatedBg', labelKey: 'themeElevatedBg' },
  { key: 'border', labelKey: 'themeBorder' },
];

const PRESET_I18N: Record<ThemePresetId, string> = {
  default: 'themePresetDefault',
  warmGoldMist: 'themePresetWarmGoldMist',
  grayOcean: 'themePresetGrayOcean',
  starPlain: 'themePresetStarPlain',
  warm: 'themePresetWarm',
  cool: 'themePresetCool',
};

function palettesEqual(a: ThemePalette, b: ThemePalette): boolean {
  return (Object.keys(a) as (keyof ThemePalette)[]).every(
    (k) => a[k].toLowerCase() === b[k].toLowerCase(),
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const { token } = theme.useToken();

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
      <Typography.Text style={{ fontSize: 13, flex: 1 }}>{label}</Typography.Text>
      <Space size={6}>
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={label}
          style={{
            width: 28,
            height: 28,
            padding: 0,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 6,
            cursor: 'pointer',
            background: 'none',
          }}
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: 84,
            height: 28,
            padding: '2px 6px',
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 6,
            fontSize: 12,
            fontFamily: 'monospace',
            background: token.colorBgContainer,
            color: token.colorText,
          }}
        />
      </Space>
    </div>
  );
}

function PresetPreview({
  presetId,
  swatches,
  titleKey,
  descKey,
}: {
  presetId: 'warmGoldMist' | 'grayOcean' | 'starPlain' | 'default';
  swatches: readonly { hex: string; key: string }[];
  titleKey: string;
  descKey: string;
}) {
  const { t } = useTranslation('account');
  const { token } = theme.useToken();
  const preset = THEME_PALETTE_PRESETS[presetId];
  const pageGradient = buildSurfaceGradients(preset).page;

  return (
    <div
      style={{
        padding: 12,
        borderRadius: 8,
        border: `1px solid ${token.colorBorderSecondary}`,
        background: pageGradient,
      }}
    >
      <Typography.Text strong style={{ fontSize: 13, color: preset.primary }}>
        {t(titleKey)}
      </Typography.Text>
      <Typography.Paragraph
        type="secondary"
        style={{ fontSize: 12, margin: '6px 0 10px', color: preset.primary, opacity: 0.78 }}
      >
        {t(descKey)}
      </Typography.Paragraph>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {swatches.map(({ hex, key }) => (
          <div key={key} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: hex,
                border: `1px solid ${preset.primary}22`,
              }}
            />
            <Typography.Text style={{ fontSize: 10, color: preset.primary, opacity: 0.7 }}>
              {t(`themeSwatch_${key}`)}
            </Typography.Text>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ThemePaletteEditor() {
  const { t } = useTranslation('account');
  const { token } = theme.useToken();
  const palette = useThemePaletteStore((s) => s.palette);
  const setColor = useThemePaletteStore((s) => s.setColor);
  const applyPreset = useThemePaletteStore((s) => s.applyPreset);
  const reset = useThemePaletteStore((s) => s.reset);

  const isWarmGoldMist = palettesEqual(palette, THEME_PALETTE_PRESETS.warmGoldMist);
  const isGrayOcean = palettesEqual(palette, THEME_PALETTE_PRESETS.grayOcean);
  const isStarPlain = palettesEqual(palette, THEME_PALETTE_PRESETS.starPlain);
  const isDefault = palettesEqual(palette, DEFAULT_THEME_PALETTE);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('themeHint')}
      </Typography.Text>

      <Space wrap>
        <Select
          size="small"
          style={{ minWidth: 160 }}
          placeholder={t('themePreset')}
          options={THEME_PRESET_ORDER.map((id) => ({
            value: id,
            label: t(PRESET_I18N[id]),
          }))}
          onChange={(value) => applyPreset(value as ThemePresetId)}
        />
        <Button size="small" onClick={reset}>
          {t('themeReset')}
        </Button>
      </Space>

      {isWarmGoldMist && (
        <PresetPreview
          presetId="warmGoldMist"
          swatches={WARM_GOLD_MIST_SWATCHES}
          titleKey="themePresetWarmGoldMist"
          descKey="themePresetWarmGoldMistDesc"
        />
      )}
      {isGrayOcean && (
        <PresetPreview
          presetId="grayOcean"
          swatches={GRAY_OCEAN_SWATCHES}
          titleKey="themePresetGrayOcean"
          descKey="themePresetGrayOceanDesc"
        />
      )}
      {isDefault && (
        <PresetPreview
          presetId="default"
          swatches={CYAN_ORANGE_MOUNTAIN_SWATCHES}
          titleKey="themePresetDefault"
          descKey="themePresetCyanOrangeMountainDesc"
        />
      )}
      {isStarPlain && (
        <PresetPreview
          presetId="starPlain"
          swatches={STAR_PLAIN_SWATCHES}
          titleKey="themePresetStarPlain"
          descKey="themePresetStarPlainDesc"
        />
      )}

      <div
        style={{
          display: 'grid',
          gap: 10,
          padding: 12,
          borderRadius: 8,
          border: `1px solid ${token.colorBorderSecondary}`,
          background: token.colorFillQuaternary,
        }}
      >
        {PALETTE_FIELDS.map(({ key, labelKey }) => (
          <ColorField
            key={key}
            label={t(labelKey)}
            value={palette[key]}
            onChange={(value) => setColor(key, value)}
          />
        ))}
      </div>
    </div>
  );
}
