import { TaskStatus } from '@/api/types';

/** AntD Tag color preset 映射，对齐 §7.2 设计稿 */
export const TASK_STATUS_COLOR: Record<TaskStatus, string> = {
  [TaskStatus.INIT]: 'blue',
  [TaskStatus.PROCESSING]: 'processing', // 自带 animated 边
  [TaskStatus.SUCCESS]: 'success',
  [TaskStatus.CANCELLED]: 'default',
  [TaskStatus.CANCEL_REQUESTED]: 'orange',
  [TaskStatus.FAILED]: 'error',
};

/** 事件源 → 主题色，timeline 上区分 task 层 vs harness 层 */
export const SOURCE_COLOR: Record<string, string> = {
  task_scheduler: '#1677ff', // 蓝
  harness: '#722ed1', // 紫
};

/** 风险等级 → tag color */
export const RISK_COLOR: Record<string, string> = {
  READ: 'green',
  WRITE: 'gold',
  DESTRUCTIVE: 'red',
};
