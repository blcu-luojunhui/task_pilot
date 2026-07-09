import { useMemo, useState } from 'react';
import { Avatar, Button, Space, Typography, Upload, message, theme } from 'antd';
import { DeleteOutlined, UploadOutlined, UserOutlined, RobotOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AvatarRole } from '@/api/auth';
import { deleteAvatar, uploadAvatar } from '@/api/auth';
import { useAuthStore } from '@/stores/authStore';
import { buildAvatarImageUrl, prepareAvatarFile } from '@/utils/avatarUrl';

interface Props {
  role: AvatarRole;
  title: string;
  showHint?: boolean;
}

export function AccountAvatarEditor({ role, title, showHint = true }: Props) {
  const { t } = useTranslation('account');
  const { token } = theme.useToken();
  const account = useAuthStore((s) => s.account);
  const authToken = useAuthStore((s) => s.token);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const [uploading, setUploading] = useState(false);

  const versionKey = role === 'user' ? account?.avatar_url : account?.agent_avatar_url;
  const imageUrl = useMemo(
    () => buildAvatarImageUrl(role, authToken, versionKey),
    [role, authToken, versionKey],
  );

  const fallbackIcon = role === 'user' ? <UserOutlined /> : <RobotOutlined />;

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const prepared = await prepareAvatarFile(file);
      const updated = await uploadAvatar(role, prepared);
      useAuthStore.setState({ account: updated });
      message.success(t('avatarUpdated'));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('avatarUploadFailed');
      message.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async () => {
    setUploading(true);
    try {
      const updated = await deleteAvatar(role);
      useAuthStore.setState({ account: updated });
      message.success(t('avatarRemoved'));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('avatarRemoveFailed');
      message.error(msg);
    } finally {
      setUploading(false);
      void fetchMe();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <Typography.Text strong style={{ fontSize: 13 }}>
        {title}
      </Typography.Text>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <Avatar
          size={56}
          src={imageUrl ?? undefined}
          icon={!imageUrl ? fallbackIcon : undefined}
          style={{
            border: `1px solid ${token.colorBorderSecondary}`,
            background: token.colorBgContainer,
            flexShrink: 0,
          }}
        />
        <Space wrap>
          <Upload
            accept="image/jpeg,image/png,image/webp,image/gif"
            showUploadList={false}
            beforeUpload={(file) => {
              void handleUpload(file);
              return false;
            }}
          >
            <Button size="small" icon={<UploadOutlined />} loading={uploading}>
              {imageUrl ? t('avatarChange') : t('avatarUpload')}
            </Button>
          </Upload>
          {imageUrl && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              loading={uploading}
              onClick={() => void handleRemove()}
            >
              {t('avatarRemove')}
            </Button>
          )}
        </Space>
      </div>
      {showHint && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('avatarHint')}
        </Typography.Text>
      )}
    </div>
  );
}
