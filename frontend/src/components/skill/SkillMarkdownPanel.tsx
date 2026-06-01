import { useMemo } from 'react';
import { Button, Card, Input, Space, Tag, Typography, theme } from 'antd';
import { DeleteOutlined, HistoryOutlined, SaveOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { SkillInfo } from '@/api/types';
import { RISK_COLOR } from '@/utils/colors';

interface Props {
  skill: SkillInfo | null;
  draft?: string;
  editing?: boolean;
  dirty?: boolean;
  saving?: boolean;
  onDraftChange?: (value: string) => void;
  onSave?: () => void;
  onDelete?: () => void;
  onShowCalls?: () => void;
}

function riskTagColor(level: string): string | undefined {
  return RISK_COLOR[level.toUpperCase()];
}

function splitFrontmatter(content: string): { frontmatter: string; body: string } {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('---')) {
    return { frontmatter: '', body: content };
  }

  const lines = trimmed.split('\n');
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === '---');
  if (end < 0) {
    return { frontmatter: '', body: content };
  }

  return {
    frontmatter: lines.slice(1, end).join('\n').trim(),
    body: lines.slice(end + 1).join('\n').trim(),
  };
}

export function SkillMarkdownPanel({
  skill,
  draft = '',
  editing = false,
  dirty = false,
  saving = false,
  onDraftChange,
  onSave,
  onDelete,
  onShowCalls,
}: Props) {
  const { token } = theme.useToken();
  const content = editing ? draft : skill?.markdown ?? '';
  const { frontmatter, body } = useMemo(() => splitFrontmatter(content), [content]);
  const previewContent = body || content;

  const preview = useMemo(
    () => (
      <Card
        variant="borderless"
        styles={{
          body: {
            padding: '20px 24px',
            maxWidth: 920,
          },
        }}
        style={{ minHeight: 480, overflow: 'auto' }}
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <Typography.Title level={3} style={{ marginTop: 0 }}>
                {children}
              </Typography.Title>
            ),
            h2: ({ children }) => (
              <Typography.Title level={4} style={{ marginTop: 24 }}>
                {children}
              </Typography.Title>
            ),
            h3: ({ children }) => (
              <Typography.Title level={5} style={{ marginTop: 20 }}>
                {children}
              </Typography.Title>
            ),
            p: ({ children }) => (
              <Typography.Paragraph style={{ lineHeight: 1.8, marginBottom: 12 }}>
                {children}
              </Typography.Paragraph>
            ),
            pre: ({ children }) => (
              <pre
                style={{
                  background: token.colorFillTertiary,
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: token.borderRadius,
                  fontSize: 13,
                  lineHeight: 1.7,
                  overflow: 'auto',
                  padding: 12,
                }}
              >
                {children}
              </pre>
            ),
          }}
        >
          {previewContent}
        </ReactMarkdown>
      </Card>
    ),
    [previewContent, token.borderRadius, token.colorBorderSecondary, token.colorFillTertiary]
  );

  if (!skill && !editing) {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: token.colorTextSecondary,
        }}
      >
        选择左侧 Markdown 文件查看内容
      </div>
    );
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%', height: '100%' }}>
      <Card
        size="small"
        styles={{ body: { padding: '12px 16px' } }}
        style={{ borderColor: token.colorBorderSecondary }}
      >
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space direction="vertical" size={4}>
            <Space wrap>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {skill?.name ?? '新建 Skill'}
              </Typography.Title>
              {skill && <Tag color={riskTagColor(String(skill.risk_level))}>{skill.risk_level}</Tag>}
              {skill && <Tag>{skill.category}</Tag>}
              {skill?.source === 'system' && <Tag color="blue">只读</Tag>}
              {(skill?.source === 'personal' || editing) && <Tag color="green">可编辑</Tag>}
            </Space>
            {skill?.description && (
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                {skill.description}
              </Typography.Text>
            )}
          </Space>
          <Space wrap>
            {skill?.source === 'system' && onShowCalls && (
              <Button size="small" icon={<HistoryOutlined />} onClick={onShowCalls}>
                Recent Calls
              </Button>
            )}
            {editing && (
              <>
                <Button
                  type="primary"
                  size="small"
                  icon={<SaveOutlined />}
                  loading={saving}
                  disabled={!dirty}
                  onClick={onSave}
                >
                  保存
                </Button>
                {skill && (
                  <Button danger size="small" icon={<DeleteOutlined />} onClick={onDelete}>
                    删除
                  </Button>
                )}
              </>
            )}
          </Space>
        </Space>
      </Card>

      {frontmatter && !editing && (
        <Typography.Text type="secondary" style={{ fontSize: 12, paddingInline: 4 }}>
          frontmatter 已隐藏，用于保存 name / category / scope 等元数据
        </Typography.Text>
      )}

      {editing ? (
        <Input.TextArea
          value={draft}
          onChange={(e) => onDraftChange?.(e.target.value)}
          autoSize={{ minRows: 22, maxRows: 32 }}
          style={{
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 13,
          }}
        />
      ) : (
        preview
      )}
    </Space>
  );
}
