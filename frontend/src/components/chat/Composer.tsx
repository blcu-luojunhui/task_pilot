import { KeyboardEvent, useRef, useState } from 'react';
import { Button, Input, Space, theme } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface Props {
  disabled?: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, onSend }: Props) {
  const { token } = theme.useToken();
  const [value, setValue] = useState('');
  const textAreaRef = useRef<HTMLTextAreaElement>(null);
  const { t } = useTranslation('chat');

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue('');
    setTimeout(() => textAreaRef.current?.focus(), 0);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <Space.Compact style={{ width: '100%' }}>
      <Input.TextArea
        ref={textAreaRef}
        autoSize={{ minRows: 1, maxRows: 6 }}
        placeholder={t('composerPlaceholder')}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        style={{
          borderRadius: '12px 0 0 12px',
          background: token.colorFillQuaternary,
          border: `1px solid ${token.colorBorderSecondary}`,
        }}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        disabled={disabled || !value.trim()}
        onClick={submit}
        style={{
          height: 'auto',
          borderRadius: '0 12px 12px 0',
          background: 'linear-gradient(135deg, #5ac8fa 0%, #007aff 100%)',
          border: 'none',
          boxShadow: '0 2px 8px rgba(0, 122, 255, 0.2)',
          minWidth: 60,
        }}
      >
        {t('send')}
      </Button>
    </Space.Compact>
  );
}
