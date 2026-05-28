import { KeyboardEvent, useRef, useState } from 'react';
import { Button, Input, Space } from 'antd';
import { SendOutlined } from '@ant-design/icons';

interface Props {
  disabled?: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, onSend }: Props) {
  const [value, setValue] = useState('');
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue('');
    setTimeout(() => textAreaRef.current?.focus(), 0);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter 发送，Shift+Enter 换行
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
        placeholder="输入消息  (Enter 发送, Shift+Enter 换行)"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        style={{ borderRadius: '10px 0 0 10px' }}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        disabled={disabled || !value.trim()}
        onClick={submit}
        style={{
          height: 'auto',
          borderRadius: '0 10px 10px 0',
          minWidth: 60,
        }}
      >
        发送
      </Button>
    </Space.Compact>
  );
}
