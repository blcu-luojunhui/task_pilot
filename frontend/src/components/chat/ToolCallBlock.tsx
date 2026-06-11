import { useCallback, useState } from 'react';
import { Card, Collapse, Space, Spin, Tag, Typography, theme } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  LoadingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
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

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const { t } = useTranslation('chat');

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <Typography.Link onClick={handleCopy} style={{ fontSize: 12 }}>
      <CopyOutlined /> {copied ? t('copied') : label}
    </Typography.Link>
  );
}

export function ToolCallBlock({ toolCall }: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');

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
      ? t('executing')
      : toolCall.status === 'completed'
        ? t('completed')
        : t('failed');

  const statusColor =
    toolCall.status === 'running'
      ? 'processing'
      : toolCall.status === 'completed'
        ? 'success'
        : 'error';

  const argsText = formatArgs(toolCall.arguments);
  const resultText = formatResult(toolCall.result);

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', padding: '4px 12px' }}>
      <div style={{ maxWidth: '80%' }}>
        <Card
          size="small"
          style={{
            background: token.colorBgLayout,
            borderColor:
              toolCall.status === 'failed' ? token.colorErrorBorder : token.colorBorderSecondary,
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
                label: (
                  <Space>
                    <span>{t('paramsLabel')}</span>
                    <CopyButton text={argsText} label={t('copyCode')} />
                  </Space>
                ),
                children: (
                  <pre className="tool-result-pre">{argsText}</pre>
                ),
              },
              ...(toolCall.status === 'completed' || toolCall.status === 'failed'
                ? [
                    {
                      key: 'result',
                      label: (
                        <Space>
                          <span>
                            {toolCall.status === 'completed' ? t('resultLabel') : t('errorLabel')}
                          </span>
                          {resultText ? (
                            <CopyButton text={resultText} label={t('copyCode')} />
                          ) : null}
                        </Space>
                      ),
                      children: (
                        <pre
                          className="tool-result-pre"
                          style={{
                            color: toolCall.status === 'failed' ? token.colorError : undefined,
                          }}
                        >
                          {resultText}
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
