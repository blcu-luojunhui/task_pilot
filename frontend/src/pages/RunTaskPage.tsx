import { useEffect, useRef, useCallback } from 'react';
import {
  Button,
  Input,
  Layout,
  Space,
  Tag,
  Typography,
  theme,
  Card,
  message,
} from 'antd';
import {
  PlayCircleOutlined,
  CloseCircleOutlined,
  SettingOutlined,
  AimOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  CopyOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useRunTaskStore } from '@/stores/runTaskStore';
import { useChatTurnStream } from '@/hooks/useChatTurnStream';
import { useTranslation } from 'react-i18next';
import { ToolCallBlock } from '@/components/chat/ToolCallBlock';
import '@/components/chat/ChatMessage.css';

const { TextArea } = Input;

interface AreaMeta {
  label: string;
  icon: string;
  color: string;
}

const AREA_META: Record<string, AreaMeta> = {
  chat_ops: { label: 'Chat Ops', icon: '💬', color: 'blue' },
  database: { label: 'Database', icon: '🗄️', color: 'green' },
  http: { label: 'HTTP', icon: '🌐', color: 'orange' },
  task: { label: 'Task', icon: '📋', color: 'purple' },
  utils: { label: 'Utils', icon: '🔧', color: 'default' },
};


function MarkdownRenderer({ content, token }: { content: string; token: ReturnType<typeof theme.useToken>['token'] }) {
  return (
    <div className="markdown-body" style={{ fontSize: 13 }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  style={{ background: token.colorFillTertiary, padding: '1px 5px', borderRadius: 4, fontSize: '0.88em' }}
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <pre style={{ background: token.colorFillTertiary, padding: 12, borderRadius: 6, overflow: 'auto' }}>
                <code className={className} {...props}>{children}</code>
              </pre>
            );
          },
          a({ href, children, ...props }) {
            return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
          },
          table({ children, ...props }) {
            return (
              <div style={{ overflow: 'auto' }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }} {...props}>{children}</table>
              </div>
            );
          },
          th({ children, ...props }) {
            return (
              <th
                style={{ border: `1px solid ${token.colorBorderSecondary}`, padding: '8px 12px', background: token.colorFillTertiary, fontWeight: 600, textAlign: 'left' }}
                {...props}
              >
                {children}
              </th>
            );
          },
          td({ children, ...props }) {
            return (
              <td style={{ border: `1px solid ${token.colorBorderSecondary}`, padding: '8px 12px' }} {...props}>
                {children}
              </td>
            );
          },
          hr() {
            return <hr style={{ border: 'none', borderTop: `1px solid ${token.colorBorderSecondary}` }} />;
          },
          blockquote({ children, ...props }) {
            return (
              <blockquote style={{ borderLeft: `3px solid ${token.colorPrimaryBorder}`, color: token.colorTextSecondary }} {...props}>
                {children}
              </blockquote>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function RunTaskPage() {
  const { t } = useTranslation('runTask');
  const { token } = theme.useToken();

  const areaDesc: Record<string, string> = {
    chat_ops: t('chatOpsDesc'),
    database: t('databaseDesc'),
    http: t('httpDesc'),
    task: t('taskDesc'),
    utils: t('utilsDesc'),
  };

  const toolAreas = useRunTaskStore((s) => s.toolAreas);
  const selectedAreas = useRunTaskStore((s) => s.selectedAreas);
  const goal = useRunTaskStore((s) => s.goal);
  const traceId = useRunTaskStore((s) => s.traceId);
  const inFlight = useRunTaskStore((s) => s.inFlight);
  const streamingText = useRunTaskStore((s) => s.streamingText);
  const toolCalls = useRunTaskStore((s) => s.toolCalls);
  const finalResult = useRunTaskStore((s) => s.finalResult);
  const error = useRunTaskStore((s) => s.error);

  const fetchToolAreas = useRunTaskStore((s) => s.fetchToolAreas);
  const setGoal = useRunTaskStore((s) => s.setGoal);
  const toggleArea = useRunTaskStore((s) => s.toggleArea);
  const run = useRunTaskStore((s) => s.run);
  const cancel = useRunTaskStore((s) => s.cancel);
  const handleLiveEvent = useRunTaskStore((s) => s.handleLiveEvent);

  const initialized = useRef(false);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    fetchToolAreas();
  }, [fetchToolAreas]);

  // SSE 订阅
  useChatTurnStream(traceId, {
    enabled: Boolean(traceId),
    onEvent: (e) => handleLiveEvent(e),
  });

  // 流式输出时自动滚到底部
  useEffect(() => {
    if (outputRef.current && (streamingText || toolCalls.length > 0)) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [streamingText, toolCalls]);

  const handleRun = useCallback(async () => {
    await run();
  }, [run]);

  const handleCopyResult = useCallback(() => {
    if (finalResult) {
      navigator.clipboard.writeText(finalResult).then(
        () => message.success(t('copied')),
        () => message.error(t('copyFailed')),
      );
    }
  }, [finalResult]);

  const hasOutput = inFlight || finalResult || error || streamingText || toolCalls.length > 0;

  return (
    <Layout
      hasSider
      style={{
        height: 'calc(100vh - 56px - 48px)',
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {/* ═══ 左栏：配置区 ═══ */}
      <div
        style={{
          width: 320,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          background: token.colorBgContainer,
        }}
      >
        {/* 标题 */}
        <div
          style={{
            padding: '16px 16px 12px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Space align="center" size={8}>
            <ThunderboltOutlined style={{ fontSize: 18, color: token.colorPrimary }} />
            <Typography.Text strong style={{ fontSize: 15 }}>{t('title')}</Typography.Text>
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
            {t('subtitle')}
          </Typography.Text>
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* Goal */}
          <div style={{ padding: '16px 16px 8px' }}>
            <Space size={4} style={{ marginBottom: 8 }}>
              <AimOutlined style={{ color: token.colorPrimary }} />
              <Typography.Text strong style={{ fontSize: 13 }}>{t('goal')}</Typography.Text>
            </Space>
            <TextArea
              placeholder={t('goalPlaceholder')}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={4}
              disabled={inFlight}
              style={{ fontSize: 13, resize: 'none' }}
            />
          </div>

          {/* Skills */}
          <div style={{ padding: '8px 16px' }}>
            <Space size={4} style={{ marginBottom: 8 }}>
              <SettingOutlined style={{ color: token.colorWarning }} />
              <Typography.Text strong style={{ fontSize: 13 }}>{t('skills')}</Typography.Text>
              {selectedAreas.length > 0 && (
                <Tag style={{ marginLeft: 4 }}>{t('skillsCount', { count: selectedAreas.length })}</Tag>
              )}
            </Space>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {toolAreas.map((area) => {
                const meta = AREA_META[area] || { label: area, icon: '📦', color: 'default' };
                const selected = selectedAreas.includes(area);
                return (
                  <div
                    key={area}
                    onClick={() => !inFlight && toggleArea(area)}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      cursor: inFlight ? 'not-allowed' : 'pointer',
                      border: `1px solid ${selected ? token.colorPrimary : token.colorBorderSecondary}`,
                      background: selected ? token.colorPrimaryBg : token.colorBgContainer,
                      opacity: inFlight ? 0.6 : 1,
                      transition: 'all 0.2s',
                    }}
                  >
                    <Space size={6}>
                      <span>{meta.icon}</span>
                      <div>
                        <Typography.Text
                          style={{ fontSize: 12, fontWeight: selected ? 600 : 400 }}
                        >
                          {meta.label}
                        </Typography.Text>
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 11, display: 'block', lineHeight: 1.4 }}
                        >
                          {areaDesc[area] || ''}
                        </Typography.Text>
                      </div>
                      {selected && (
                        <CheckCircleOutlined style={{ color: token.colorPrimary, marginLeft: 'auto' }} />
                      )}
                    </Space>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* 操作按钮 */}
        <div style={{ padding: '12px 16px', borderTop: `1px solid ${token.colorBorderSecondary}` }}>
          <Button
            block
            size="large"
            type="primary"
            icon={inFlight ? <LoadingOutlined /> : <PlayCircleOutlined />}
            onClick={handleRun}
            loading={inFlight}
            disabled={!goal.trim() || selectedAreas.length === 0}
          >
            {inFlight ? t('executing') : t('run')}
          </Button>
          {inFlight && (
            <Button
              block
              danger
              size="small"
              icon={<CloseCircleOutlined />}
              onClick={() => void cancel()}
              style={{ marginTop: 8 }}
            >
              {t('cancelExecution')}
            </Button>
          )}
        </div>
      </div>

      {/* ═══ 右栏：输出区 ═══ */}
      <div
        ref={outputRef}
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: token.colorBgLayout,
          overflow: 'auto',
        }}
      >
        {/* 空状态 */}
        {!hasOutput && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: 16,
              padding: 48,
            }}
          >
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: '50%',
                background: token.colorFillTertiary,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ThunderboltOutlined style={{ fontSize: 32, color: token.colorTextQuaternary }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <Typography.Title level={5} type="secondary" style={{ margin: 0 }}>
                {t('ready')}
              </Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                {t('readyHint')}
              </Typography.Text>
            </div>
            <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
              {[
                { step: 1, text: t('step1') },
                { step: 2, text: t('step2') },
                { step: 3, text: t('step3') },
              ].map((s) => (
                <div key={s.step} style={{ textAlign: 'center' }}>
                  <div
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: '50%',
                      background: token.colorFillTertiary,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      fontWeight: 600,
                      color: token.colorTextSecondary,
                      marginBottom: 4,
                    }}
                  >
                    {s.step}
                  </div>
                  <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                    {s.text}
                  </Typography.Text>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 内容区 */}
        {hasOutput && (
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {/* 运行状态条 */}
            {inFlight && traceId && (
              <Card size="small" style={{ background: token.colorInfoBg, borderColor: token.colorInfoBorder }}>
                <Space size={12}>
                  <Tag color="processing" icon={<LoadingOutlined />}>{t('executing')}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }} copyable={{ text: traceId }}>
                    <code style={{ fontSize: 11 }}>{traceId}</code>
                  </Typography.Text>
                </Space>
              </Card>
            )}

            {/* 错误 */}
            {error && (
              <Card size="small" style={{ background: token.colorErrorBg, borderColor: token.colorErrorBorder }}>
                <Typography.Text type="danger" style={{ fontSize: 13 }}>{error}</Typography.Text>
              </Card>
            )}

            {/* 流式输出 */}
            {streamingText && (
              <Card
                size="small"
                title={
                  <Space size={4}>
                    <LoadingOutlined style={{ color: token.colorPrimary }} />
                    <span>{t('realtimeOutput')}</span>
                  </Space>
                }
              >
                <MarkdownRenderer content={streamingText} token={token} />
              </Card>
            )}

            {/* 工具调用 */}
            {toolCalls.map((tc) => (
              <ToolCallBlock key={tc.callId} toolCall={tc} />
            ))}

            {/* 最终结果 */}
            {finalResult && (
              <Card
                size="small"
                title={
                  <Space size={4}>
                    <CheckCircleOutlined style={{ color: token.colorSuccess }} />
                    <span>{t('completed')}</span>
                  </Space>
                }
                extra={
                  <Button
                    size="small"
                    type="text"
                    icon={<CopyOutlined />}
                    onClick={handleCopyResult}
                  >
                    {t('copy')}
                  </Button>
                }
                style={{
                  borderColor: token.colorSuccessBorder,
                  background: token.colorSuccessBg,
                }}
              >
                <MarkdownRenderer content={finalResult} token={token} />
              </Card>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}
