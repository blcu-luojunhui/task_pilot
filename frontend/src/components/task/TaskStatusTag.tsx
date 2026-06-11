import { Tag } from 'antd';
import { TaskStatus, TASK_STATUS_LABEL_KEYS } from '@/api/types';
import { TASK_STATUS_COLOR } from '@/utils/colors';
import { useTranslation } from 'react-i18next';

interface Props {
  status: TaskStatus;
}

export function TaskStatusTag({ status }: Props) {
  const { t } = useTranslation('tasks');
  return <Tag color={TASK_STATUS_COLOR[status]}>{t(TASK_STATUS_LABEL_KEYS[status])}</Tag>;
}
