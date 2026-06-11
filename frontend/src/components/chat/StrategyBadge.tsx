import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

const STRATEGY_COLORS: Record<string, string> = {
  react: 'blue',
  plan_execute: 'purple',
  reflexion: 'orange',
};

interface Props {
  strategy: string | null;
}

/** 当前策略模式标识（FE-1 / OPT-1） */
export function StrategyBadge({ strategy }: Props) {
  const { t } = useTranslation('chat');

  if (!strategy) return null;

  const labelKey = `strategy.${strategy}` as const;
  const label = t(labelKey, { defaultValue: strategy });

  return (
    <Tooltip title={t('strategyHint')}>
      <Tag color={STRATEGY_COLORS[strategy] ?? 'default'}>{label}</Tag>
    </Tooltip>
  );
}
