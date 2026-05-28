import { Alert, Card, Input, Space, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';

export function TracesPage() {
  const navigate = useNavigate();

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="Traces — Phase 2 完整版"
        description="本页将展示最近 Agent 运行列表 + 直查 trace_id。当前先提供一个直查入口；详情视图复用 /tasks/<trace_id>。"
      />
      <Card variant="borderless">
        <Typography.Title level={5}>按 trace_id 直查</Typography.Title>
        <Input.Search
          placeholder="例如 Agent-20260513184501-a1b2c3d4e5f60001"
          enterButton="跳转详情"
          allowClear
          onSearch={(v) => {
            const trimmed = v.trim();
            if (trimmed) navigate(`/tasks/${encodeURIComponent(trimmed)}`);
          }}
        />
      </Card>
    </Space>
  );
}
