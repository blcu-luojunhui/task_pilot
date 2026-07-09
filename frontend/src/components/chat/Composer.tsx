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

  const canSend = !disabled && !!value.trim();

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
          background: '#FFFFFF',
          border: `1px solid ${token.colorBorderSecondary}`,
        }}
      />
      <Button
        icon={<SendOutlined />}
        disabled={!canSend}
        onClick={submit}
        style={{
          height: 'auto',
          borderRadius: '0 12px 12px 0',
          boxShadow: 'none',
          minWidth: 60,
          ...(canSend
            ? {
                background: 'var(--color-accent)',
                borderColor: 'var(--color-accent)',
                color: '#fff',
              }
            : {
                background: token.colorFillQuaternary,
                borderColor: token.colorBorderSecondary,
                color: token.colorTextQuaternary,
              }),
        }}
      >
        {t('send')}
      </Button>
    </Space.Compact>
  );
}
