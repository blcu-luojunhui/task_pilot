import { Collapse, Typography, theme } from 'antd';
import { BulbOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { MarkdownContent } from './MarkdownContent';

interface Props {
  text: string;
  /** reflection 用不同 accent */
  variant?: 'reasoning' | 'reflection';
  streaming?: boolean;
}

/** 可折叠思考/反思块（FE-1 / OPT-3 / OPT-14） */
export function ReasoningBlock({
  text,
  variant = 'reasoning',
  streaming = false,
}: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');

  if (!text.trim()) return null;

  const isReflection = variant === 'reflection';
  const accentBg = isReflection ? token.colorWarningBg : token.colorFillTertiary;
  const accentBorder = isReflection ? token.colorWarningBorder : token.colorBorderSecondary;

  return (
    <div style={{ margin: '4px 0' }}>
      <Collapse
        size="small"
        defaultActiveKey={streaming ? ['reasoning'] : []}
        items={[
          {
            key: 'reasoning',
            label: (
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                <BulbOutlined style={{ marginRight: 6 }} />
                {isReflection ? t('reflectionTitle') : t('reasoningTitle')}
                {streaming && ` ${t('reasoningStreaming')}`}
              </Typography.Text>
            ),
            children: (
              <div
                style={{
                  background: accentBg,
                  border: `1px solid ${accentBorder}`,
                  borderRadius: 8,
                  padding: '8px 12px',
                  fontSize: 13,
                }}
                aria-live={streaming ? 'polite' : undefined}
              >
                <MarkdownContent content={text} />
                {streaming && <span className="typing-cursor" />}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
