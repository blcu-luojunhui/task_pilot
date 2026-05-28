import { Card, Collapse, Space, Spin, Tag, Typography, theme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import type { ToolCallStatus } from '@/stores/chatStore';

interface Props {
  toolCall: ToolCallStatus;
}

function formatArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 2);
  } catch {
    return String(args);
  }
}

function formatResult(result: unknown): string {
  if (result === undefined || result === null) return '';
  if (typeof result === 'string') {
    try {
      return JSON.stringify(JSON.parse(result), null, 2);
    } catch {
      return result;
    }
  }
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

export function ToolCallBlock({ toolCall }: Props) {
  const { token } = theme.useToken();

  const statusIcon =
    toolCall.status === 'running' ? (
      <Spin indicator={<LoadingOutlined spin />} size="small" />
    ) : toolCall.status === 'completed' ? (
      <CheckCircleOutlined style={{ color: token.colorSuccess }} />
    ) : (
      <CloseCircleOutlined style={{ color: token.colorError }} />
    );

  const statusLabel =
    toolCall.status === 'running'
      ? '执行中'
      : toolCall.status === 'completed'
        ? '完成'
        : '失败';

  const statusColor =
    toolCall.status === 'running'
      ? 'processing'
      : toolCall.status === 'completed'
        ? 'success'
        : 'error';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'flex-start',
        padding: '4px 12px',
      }}
    >
      <div style={{ maxWidth: '80%' }}>
        <Card
          size="small"
          style={{
            background: token.colorBgLayout,
            borderColor:
              toolCall.status === 'failed'
                ? token.colorErrorBorder
                : token.colorBorderSecondary,
          }}
          title={
            <Space size={6}>
              {statusIcon}
              <ToolOutlined />
              <Typography.Text strong>{toolCall.toolName}</Typography.Text>
              <Tag color={statusColor}>{statusLabel}</Tag>
            </Space>
          }
        >
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
                    {formatArgs(toolCall.arguments)}
                  </pre>
                ),
              },
              ...(toolCall.status === 'completed' || toolCall.status === 'failed'
                ? [
                    {
                      key: 'result',
                      label: toolCall.status === 'completed' ? '结果' : '错误',
                      children: (
                        <pre
                          style={{
                            margin: 0,
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-all',
                            color:
                              toolCall.status === 'failed'
                                ? token.colorError
                                : undefined,
                          }}
                        >
                          {formatResult(toolCall.result)}
                        </pre>
                      ),
                    },
                  ]
                : []),
            ]}
          />
        </Card>
      </div>
    </div>
  );
}
