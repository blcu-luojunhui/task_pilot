import { Button, Card, Collapse, Space, Tag, Typography, theme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import type { ToolCall } from '@/api/types';

interface Props {
  toolCalls: ToolCall[];
  loading: boolean;
  onConfirm: () => void;
  onReject: () => void;
}

function formatArgs(argsStr: string): string {
  try {
    const parsed = JSON.parse(argsStr);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return argsStr;
  }
}

export function PendingPlanCard({ toolCalls, loading, onConfirm, onReject }: Props) {
  const { token } = theme.useToken();

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-start',
        padding: '8px 12px',
      }}
    >
      <div style={{ maxWidth: '80%', width: '100%' }}>
        <Card
          size="small"
          style={{
            background: token.colorWarningBg,
            borderColor: token.colorWarningBorder,
          }}
          title={
            <Space>
              <ExclamationCircleOutlined style={{ color: token.colorWarning }} />
              <Typography.Text strong>我打算执行以下操作</Typography.Text>
            </Space>
          }
        >
          {toolCalls.map((tc, i) => (
            <Card
              key={tc.id || i}
              size="small"
              type="inner"
              style={{ marginBottom: i < toolCalls.length - 1 ? 8 : 0 }}
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <Tag color="orange">{tc.function?.name ?? 'unknown'}</Tag>
                </Space>
                <Collapse
                  ghost
                  size="small"
                  items={[
                    {
                      key: 'args',
                      label: '参数',
                      children: (
                        <pre
                          style={{
                            margin: 0,
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-all',
                          }}
                        >
                          {formatArgs(tc.function?.arguments ?? '{}')}
                        </pre>
                      ),
                    },
                  ]}
                />
              </Space>
            </Card>
          ))}

          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <Button
              type="primary"
              icon={loading ? <LoadingOutlined /> : <CheckCircleOutlined />}
              loading={loading}
              onClick={onConfirm}
            >
              确认执行
            </Button>
            <Button
              danger
              icon={<CloseCircleOutlined />}
              disabled={loading}
              onClick={onReject}
            >
              取消
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
