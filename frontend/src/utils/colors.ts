import type { GlobalToken } from 'antd';
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

/** 事件源 → AntD Tag 色名，timeline 上区分 task 层 vs harness 层（FE-0） */
export const SOURCE_COLOR: Record<string, string> = {
  task_scheduler: 'blue',
  harness: 'purple',
  chat: 'cyan',
};

/** 风险等级 → tag color */
export const RISK_COLOR: Record<string, string> = {
  READ: 'green',
  WRITE: 'gold',
  DESTRUCTIVE: 'red',
};

/**
 * Agent 场景语义色板（FE-0）。
 *
 * 全部由 AntD GlobalToken 派生，自动随亮/暗主题切换——
 * 替代散落在组件里的硬编码 hex（如 #fff2f0 / #ff4d4f），保证暗色模式一致。
 */
export interface AgentPalette {
  /** 普通步骤/节点背景 */
  stepBg: string;
  /** 普通步骤/节点边框 */
  stepBorder: string;
  /** 错误步骤/节点背景 */
  stepErrorBg: string;
  /** 错误步骤/节点边框 */
  stepErrorBorder: string;
  /** 普通连线 */
  edge: string;
  /** 错误连线 */
  edgeError: string;
  /** 运行中 */
  running: string;
  /** 成功/完成 */
  done: string;
  /** 失败 */
  failed: string;
  /** 待执行/中性 */
  pending: string;
  /** Assistant 头像背景 / 边框 / 文字 */
  agentAvatarBg: string;
  agentAvatarBorder: string;
  agentAvatarText: string;
  /** Tool 头像背景 / 边框 / 文字 */
  toolAvatarBg: string;
  toolAvatarBorder: string;
  toolAvatarText: string;
  /** 图表/仪表盘：成功、失败、警告、强调（运行中等） */
  chartSuccess: string;
  chartError: string;
  chartWarning: string;
  chartAccent: string;
  chartNeutral: string;
  /** 多序列图表色板 */
  chartSeries: string[];
  /** 角色背景（Transcript / Prompt） */
  roleSystemBg: string;
  roleUserBg: string;
  roleAssistantBg: string;
  roleToolBg: string;
}

export function getAgentPalette(token: GlobalToken): AgentPalette {
  return {
    stepBg: token.colorFillQuaternary,
    stepBorder: token.colorBorder,
    stepErrorBg: token.colorErrorBg,
    stepErrorBorder: token.colorError,
    edge: token.colorPrimary,
    edgeError: token.colorError,
    running: token.colorPrimary,
    done: token.colorSuccess,
    failed: token.colorError,
    pending: token.colorTextQuaternary,
    agentAvatarBg: token.colorSuccessBg,
    agentAvatarBorder: token.colorSuccessBorder,
    agentAvatarText: token.colorSuccess,
    toolAvatarBg: token.colorWarningBg,
    toolAvatarBorder: token.colorWarningBorder,
    toolAvatarText: token.colorWarning,
    chartSuccess: token.colorSuccess,
    chartError: token.colorError,
    chartWarning: token.colorWarning,
    chartAccent: token.colorInfo,
    chartNeutral: token.colorTextQuaternary,
    chartSeries: [
      token.colorPrimary,
      token.colorSuccess,
      token.colorWarning,
      token.colorError,
      token.colorInfo,
      token.colorLink,
      token.colorWarningActive,
      token.colorPrimaryActive,
    ],
    roleSystemBg: token.colorFillQuaternary,
    roleUserBg: token.colorPrimaryBg,
    roleAssistantBg: token.colorWarningBg,
    roleToolBg: token.colorSuccessBg,
  };
}
