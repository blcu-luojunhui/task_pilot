import { Alert } from 'antd';
import { useTranslation } from 'react-i18next';

interface Props {
  message: string;
}

/** 上下文压缩提示（FE-3） */
export function CompactionNotice({ message }: Props) {
  const { t } = useTranslation('chat');

  return (
    <div style={{ padding: '4px 16px' }}>
      <Alert type="info" showIcon message={t('compaction.title')} description={message} />
    </div>
  );
}
