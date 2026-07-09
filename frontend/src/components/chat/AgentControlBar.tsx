import { Button, Popconfirm, Space } from 'antd';
import {
  PauseCircleOutlined,
  PlayCircleOutlined,
  SaveOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AgentLifecycleState } from '@/api/types';

interface Props {
  lifecycle: AgentLifecycleState;
  traceId: string | null;
  loading?: boolean;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onSaveSnapshot: () => void;
}

/** Agent 生命周期控制条（FE-4） */
export function AgentControlBar({
  lifecycle,
  traceId,
  loading = false,
  onPause,
  onResume,
  onStop,
  onSaveSnapshot,
}: Props) {
  const { t } = useTranslation('chat');

  if (!traceId || lifecycle === 'idle' || lifecycle === 'stopped') return null;

  return (
    <Space size={8}>
      {lifecycle === 'running' && (
        <>
          <Button
            size="small"
            icon={<PauseCircleOutlined />}
            loading={loading}
            onClick={onPause}
          >
            {t('control.pause')}
          </Button>
          <Popconfirm title={t('control.stopConfirm')} onConfirm={onStop}>
            <Button size="small" danger icon={<StopOutlined />} loading={loading}>
              {t('control.stop')}
            </Button>
          </Popconfirm>
        </>
      )}
      {lifecycle === 'paused' && (
        <>
          <Button
            size="small"
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={loading}
            onClick={onResume}
          >
            {t('control.resume')}
          </Button>
          <Button
            size="small"
            icon={<SaveOutlined />}
            loading={loading}
            onClick={onSaveSnapshot}
          >
            {t('control.snapshot')}
          </Button>
          <Popconfirm title={t('control.stopConfirm')} onConfirm={onStop}>
            <Button size="small" danger icon={<StopOutlined />} loading={loading}>
              {t('control.stop')}
            </Button>
          </Popconfirm>
        </>
      )}
    </Space>
  );
}
