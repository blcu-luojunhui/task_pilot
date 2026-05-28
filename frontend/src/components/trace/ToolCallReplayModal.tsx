import { useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Space,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import { PlayCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { apiClient } from '@/api/client';
import type { TraceEvent } from '@/api/types';

interface ToolCallInfo {
  name: string;
  arguments: unknown;
  step: number;
}

/** 从 act_end 事件的 tool_results 中提取失败的 tool call */
function extractFailedToolCall(event: TraceEvent): ToolCallInfo | null {
  const data = event.data as {
    tool_results?: Array<{ content?: string; tool_call_id?: string }>;
    tool_calls?: Array<{ name?: string; arguments?: unknown }>;
  };

  // 优先从 act_end 所在事件的关联 act_start 数据中提取
  const results = data.tool_results ?? [];
  const calls = data.tool_calls ?? [];

  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const isError = (r.content ?? '').startsWith('Error:');
    if (isError) {
      const call = calls[i] ?? { name: 'unknown', arguments: {} };
      return {
        name: call.name ?? 'unknown',
        arguments: call.arguments ?? {},
        step: event.step ?? 0,
      };
    }
  }
  return null;
}

interface Props {
  event: TraceEvent | null;
  open: boolean;
  onClose: () => void;
}

export function ToolCallReplayModal({ event, open, onClose }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; result: string } | null>(null);
  const [form] = Form.useForm();
  const { token } = theme.useToken();

  const toolCall = event ? extractFailedToolCall(event) : null;

  const handleReplay = async () => {
    if (!toolCall) return;
    try {
      const values = await form.validateFields();
      let params: Record<string, unknown>;
      try {
        params = JSON.parse(values.arguments);
      } catch {
        message.error('参数不是有效 JSON');
        return;
      }

      setSubmitting(true);
      setResult(null);
      const response = await apiClient.post<{
        code: number;
        message?: string;
        data: { success: boolean; result: string };
      }>(`/skills/${encodeURIComponent(toolCall.name)}/invoke`, {
        params,
      });

      if (response.data.code === 0) {
        setResult(response.data.data);
      } else {
        message.warning(response.data.message ?? 'Invoke failed');
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { message?: string } } };
      message.error(e?.response?.data?.message ?? '请求失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setResult(null);
    form.resetFields();
    onClose();
  };

  return (
    <Modal
      title={
        <Space>
          <PlayCircleOutlined />
          <span>重放 Tool Call</span>
          {toolCall && <Tag color="geekblue">{toolCall.name}</Tag>}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      width={560}
      footer={
        <Space>
          <Button onClick={handleClose}>关闭</Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={submitting}
            onClick={handleReplay}
            disabled={!toolCall}
          >
            执行
          </Button>
        </Space>
      }
    >
      {!toolCall ? (
        <Alert
          type="warning"
          showIcon
          message="此事件不包含可重放的失败 tool call"
        />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            icon={<WarningOutlined />}
            message="此功能仅允许调用 READ 级别的 Skill"
            description="DESTRUCTIVE 操作被永久禁止。默认需要环境变量 TASK_PILOT_ALLOW_DIRECT_SKILL_INVOKE=true。"
          />

          <Form form={form} layout="vertical" initialValues={{
            arguments: typeof toolCall.arguments === 'object'
              ? JSON.stringify(toolCall.arguments, null, 2)
              : String(toolCall.arguments || '{}'),
          }}>
            <Form.Item label="Skill">
              <Input value={toolCall.name} disabled />
            </Form.Item>
            <Form.Item label="Step">
              <Input value={toolCall.step} disabled />
            </Form.Item>
            <Form.Item
              name="arguments"
              label="参数 (JSON)"
              rules={[
                { required: true, message: '请输入参数' },
                {
                  validator: (_, v) => {
                    try { JSON.parse(v); return Promise.resolve(); }
                    catch { return Promise.reject('非法 JSON'); }
                  },
                },
              ]}
            >
              <Input.TextArea
                rows={6}
                style={{
                  fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                  fontSize: 12,
                }}
              />
            </Form.Item>
          </Form>

          {result && (
            <div
              style={{
                padding: 12,
                borderRadius: 6,
                background: result.success ? token.colorSuccessBg : token.colorErrorBg,
                border: `1px solid ${result.success ? token.colorSuccessBorder : token.colorErrorBorder}`,
              }}
            >
              <Typography.Text strong>
                {result.success ? '成功' : '失败'}
              </Typography.Text>
              <pre style={{ margin: '8px 0 0', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {result.result}
              </pre>
            </div>
          )}
        </Space>
      )}
    </Modal>
  );
}
