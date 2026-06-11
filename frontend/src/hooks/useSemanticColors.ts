import { theme } from 'antd';
import { getAgentPalette, type AgentPalette } from '@/utils/colors';

/** Agent 场景语义色板（FE-0），亮/暗主题自动切换 */
export function useSemanticColors(): AgentPalette {
  const { token } = theme.useToken();
  return getAgentPalette(token);
}
