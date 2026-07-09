import { RobotOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';
import type { CSSProperties } from 'react';
import { useMemo } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { buildAvatarImageUrl } from '@/utils/avatarUrl';

interface Props {
  role: 'user' | 'assistant' | 'tool';
  toolStyle?: CSSProperties;
}

export function ChatAvatar({ role, toolStyle }: Props) {
  const account = useAuthStore((s) => s.account);
  const token = useAuthStore((s) => s.token);

  const imageUrl = useMemo(() => {
    if (role === 'tool') return null;
    const avatarRole = role === 'user' ? 'user' : 'agent';
    const versionKey =
      avatarRole === 'user' ? account?.avatar_url : account?.agent_avatar_url;
    return buildAvatarImageUrl(avatarRole, token, versionKey);
  }, [role, account?.avatar_url, account?.agent_avatar_url, token]);

  if (role === 'tool') {
    return (
      <div className="msg-avatar" style={toolStyle}>
        <ToolOutlined />
      </div>
    );
  }

  const Icon = role === 'user' ? UserOutlined : RobotOutlined;

  if (imageUrl) {
    return (
      <div className="msg-avatar msg-avatar--image">
        <img src={imageUrl} alt="" />
      </div>
    );
  }

  return (
    <div className="msg-avatar msg-avatar--fallback">
      <Icon />
    </div>
  );
}
