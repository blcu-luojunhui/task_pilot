import { Popover, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TokenUsage } from '@/api/types';

interface Props {
  usage: TokenUsage;
  cacheTokensSaved?: number;
}

/** 会话 token 成本透明（FE-3 / OPT-13/14） */
export function CostBadge({ usage, cacheTokensSaved = 0 }: Props) {
  const { t } = useTranslation('chat');

  if (!usage.total) return null;

  const content = (
    <div style={{ minWidth: 160 }}>
      <Typography.Text style={{ display: 'block' }}>
        {t('cost.prompt')}: {usage.prompt.toLocaleString()}
      </Typography.Text>
      <Typography.Text style={{ display: 'block' }}>
        {t('cost.completion')}: {usage.completion.toLocaleString()}
      </Typography.Text>
      <Typography.Text style={{ display: 'block' }}>
        {t('cost.total')}: {usage.total.toLocaleString()}
      </Typography.Text>
      {cacheTokensSaved > 0 && (
        <Typography.Text type="success" style={{ display: 'block', marginTop: 4 }}>
          {t('cost.cacheSaved', { count: cacheTokensSaved.toLocaleString() })}
        </Typography.Text>
      )}
    </div>
  );

  return (
    <Popover content={content} title={t('cost.title')}>
      <Tag color="default">{t('cost.badge', { total: usage.total.toLocaleString() })}</Tag>
    </Popover>
  );
}
