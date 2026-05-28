import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Col,
  Descriptions,
  Empty,
  Input,
  Modal,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  PlayCircleOutlined,
  ReloadOutlined,
  SwapOutlined,
} from '@ant-design/icons';
import { replayTrace } from '@/api/replay';
import type { ReplayResult } from '@/api/types';

interface Props {
  traceId: string | null;
  open: boolean;
  onClose: () => void;
}

export function CompareView({ traceId, open, onClose }: Props) {
  const [result, setResult] = useState<ReplayResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('');

  const run = async () => {
    if (!traceId) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await replayTrace({
        trace_id: traceId,
        model: model.trim() || undefined,
      });
      setResult(res);
    } catch (err: unknown) {
      const e = err as { message?: string };
      message.error(e.message ?? 'Replay 失败');
    } finally {
      setLoading(false);
    }
  };

  // 自动执行
  useEffect(() => {
    if (open && traceId) run();
    if (!open) setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, traceId]);

  const handleClose = () => {
    setResult(null);
    onClose();
  };

  return (
    <Modal
      title={
        <Space>
          <SwapOutlined />
          <span>Replay / Time Travel</span>
          {result && <Tag color="blue">{result.model}</Tag>}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      width={900}
      footer={
        <Space>
          <Button onClick={handleClose}>关闭</Button>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={run}
          >
            重新执行
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="Time Travel 将历史 trace 的最后一个 prompt 重新发给 LLM，对比新旧结果差异"
          description="当前仅重放最后一个 step 的完整 prompt（含历史对话）。模型默认使用 LLM_ 环境变量配置。"
        />

        {loading && <Spin tip="正在调用 LLM..." />}

        {result && !loading && (
          <>
            <Space size={8} wrap>
              <Tag color="purple">Step {result.step}</Tag>
              <Tag>{result.prompt_message_count} messages</Tag>
              <ModelInput model={model} onChange={setModel} />
            </Space>

            <Row gutter={16}>
              <Col span={12}>
                <div
                  style={{
                    background: '#fafafa',
                    borderRadius: 8,
                    padding: 12,
                    border: '1px solid #e8e8e8',
                  }}
                >
                  <Typography.Title level={5} style={{ margin: 0 }}>
                    <Tag color="default">原版</Tag>
                    Original
                  </Typography.Title>
                  <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
                    <Descriptions.Item label="Tokens">
                      {result.original.token_usage ? (
                        <Space size={4}>
                          <Tag>P: {result.original.token_usage.prompt.toLocaleString()}</Tag>
                          <Tag>C: {result.original.token_usage.completion.toLocaleString()}</Tag>
                          <Tag color="blue">Σ: {result.original.token_usage.total.toLocaleString()}</Tag>
                        </Space>
                      ) : (
                        'N/A'
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                  {result.original.final_answer ? (
                    <div
                      style={{
                        maxHeight: 300,
                        overflow: 'auto',
                        fontSize: 12,
                        fontFamily: 'ui-monospace, monospace',
                        whiteSpace: 'pre-wrap',
                        marginTop: 8,
                      }}
                    >
                      {result.original.final_answer}
                    </div>
                  ) : (
                    <Empty description="无 final_answer" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </div>
              </Col>

              <Col span={12}>
                <div
                  style={{
                    background: '#f6ffed',
                    borderRadius: 8,
                    padding: 12,
                    border: '1px solid #b7eb8f',
                  }}
                >
                  <Typography.Title level={5} style={{ margin: 0 }}>
                    <Tag color="green">重放</Tag>
                    Replay
                  </Typography.Title>
                  <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
                    <Descriptions.Item label="Tokens">
                      {result.replay.token_usage ? (
                        <Space size={4}>
                          <Tag>P: {result.replay.token_usage.prompt.toLocaleString()}</Tag>
                          <Tag>C: {result.replay.token_usage.completion.toLocaleString()}</Tag>
                          <Tag color="blue">Σ: {result.replay.token_usage.total.toLocaleString()}</Tag>
                        </Space>
                      ) : (
                        'N/A'
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                  {result.replay.final_answer ? (
                    <div
                      style={{
                        maxHeight: 300,
                        overflow: 'auto',
                        fontSize: 12,
                        fontFamily: 'ui-monospace, monospace',
                        whiteSpace: 'pre-wrap',
                        marginTop: 8,
                      }}
                    >
                      {result.replay.final_answer}
                    </div>
                  ) : (
                    <Empty description="无 final_answer" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </div>
              </Col>
            </Row>
          </>
        )}

        {!result && !loading && (
          <Empty description="点击「重新执行」开始 Time Travel" />
        )}
      </Space>
    </Modal>
  );
}

function ModelInput({ model, onChange }: { model: string; onChange: (v: string) => void }) {
  return (
    <Input
      size="small"
      placeholder="模型覆盖（可选）"
      value={model}
      onChange={(e) => onChange(e.target.value)}
      style={{ width: 160 }}
      prefix={<PlayCircleOutlined />}
    />
  );
}
