import { useState } from 'react';
import { Button, Card, Drawer, Spin, Typography, theme } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ArtifactRef } from '@/api/types';
import { getArtifact } from '@/api/artifacts';

interface Props {
  artifact: ArtifactRef;
}

/** 工件引用卡片，懒加载完整内容（FE-3 / OPT-5） */
export function ArtifactCard({ artifact }: Props) {
  const { token } = theme.useToken();
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const loadContent = async (nextOffset = 0, append = false) => {
    setLoading(true);
    try {
      const data = await getArtifact(artifact.id, nextOffset);
      setContent((prev) => (append && prev ? prev + data.content : data.content));
      setOffset(nextOffset + data.content.length);
      setHasMore(data.has_more);
    } catch {
      setContent(t('artifact.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    setOpen(true);
    if (content === null) {
      void loadContent(0);
    }
  };

  return (
    <>
      <Card
        size="small"
        style={{
          background: token.colorInfoBg,
          borderColor: token.colorInfoBorder,
          maxWidth: 360,
        }}
        onClick={handleOpen}
        hoverable
      >
        <Typography.Text>
          <FileTextOutlined style={{ marginRight: 6 }} />
          {artifact.summary || t('artifact.unnamed')}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ display: 'block', fontSize: 11, marginTop: 4 }}>
          {artifact.id}
        </Typography.Text>
      </Card>

      <Drawer
        title={t('artifact.viewFull')}
        open={open}
        onClose={() => setOpen(false)}
        width={560}
      >
        {loading && !content ? (
          <Spin />
        ) : (
          <>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                fontSize: 12,
                background: token.colorFillTertiary,
                padding: 12,
                borderRadius: 8,
                maxHeight: '70vh',
                overflow: 'auto',
              }}
            >
              {content}
            </pre>
            {hasMore && (
              <Button
                style={{ marginTop: 12 }}
                loading={loading}
                onClick={() => void loadContent(offset, true)}
              >
                {t('artifact.loadMore')}
              </Button>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}
