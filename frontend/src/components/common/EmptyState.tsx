import { Empty, Card } from 'antd';
import type { ReactNode } from 'react';

interface Props {
  description?: ReactNode;
  extra?: ReactNode;
}

export function EmptyState({ description, extra }: Props) {
  return (
    <Card variant="borderless">
      <Empty description={description ?? '暂无数据'}>{extra}</Empty>
    </Card>
  );
}
