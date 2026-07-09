import { Empty, Card } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  description?: ReactNode;
  extra?: ReactNode;
}

export function EmptyState({ description, extra }: Props) {
  const { t } = useTranslation('common');
  return (
    <Card variant="borderless">
      <Empty description={description ?? t('empty.noData')}>{extra}</Empty>
    </Card>
  );
}
