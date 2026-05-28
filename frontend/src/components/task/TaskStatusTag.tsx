import { Tag } from 'antd';
import { TaskStatus, TASK_STATUS_LABEL } from '@/api/types';
import { TASK_STATUS_COLOR } from '@/utils/colors';

interface Props {
  status: TaskStatus;
}

export function TaskStatusTag({ status }: Props) {
  return <Tag color={TASK_STATUS_COLOR[status]}>{TASK_STATUS_LABEL[status]}</Tag>;
}
