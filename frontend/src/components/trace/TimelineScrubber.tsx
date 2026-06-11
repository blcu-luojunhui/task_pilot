import { useEffect, useMemo, useState } from 'react';
import { Button, Slider, Space, Typography, theme } from 'antd';
import { CaretRightOutlined, PauseOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TraceEvent } from '@/api/types';

interface Props {
  events: TraceEvent[];
  selectedStep: number | null;
  onStepChange: (step: number | null) => void;
}

/** 轨迹时间轴 scrubber + 步进回放（FE-4 / OPT-12） */
export function TimelineScrubber({ events, selectedStep, onStepChange }: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('trace');
  const [playing, setPlaying] = useState(false);

  const maxStep = useMemo(() => {
    let max = 0;
    for (const e of events) {
      if (e.step != null) max = Math.max(max, e.step);
    }
    return max;
  }, [events]);

  useEffect(() => {
    if (!playing || maxStep < 1) return;
    const id = window.setInterval(() => {
      const current = selectedStep ?? 0;
      const next = current + 1;
      if (next > maxStep) {
        setPlaying(false);
        onStepChange(maxStep);
        return;
      }
      onStepChange(next);
    }, 900);
    return () => window.clearInterval(id);
  }, [playing, maxStep, selectedStep, onStepChange]);

  if (maxStep < 1) return null;

  return (
    <div
      style={{
        padding: '12px 16px',
        borderTop: `1px solid ${token.colorBorderSecondary}`,
        background: token.colorBgLayout,
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={4}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('scrubber.label', { step: selectedStep ?? 0, max: maxStep })}
          </Typography.Text>
          <Button
            size="small"
            type={playing ? 'default' : 'primary'}
            icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={() => setPlaying((p) => !p)}
          >
            {playing ? t('scrubber.pause') : t('scrubber.play')}
          </Button>
        </Space>
        <Slider
          min={0}
          max={maxStep}
          value={selectedStep ?? 0}
          marks={{
            0: '0',
            [maxStep]: String(maxStep),
          }}
          tooltip={{ formatter: (v) => `Step ${v}` }}
          onChange={(v) => {
            setPlaying(false);
            onStepChange(v === 0 ? null : v);
          }}
        />
      </Space>
    </div>
  );
}
