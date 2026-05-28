import { useEffect, useState } from 'react';
import { Button, DatePicker, Drawer, Form, Input, message, Select, Space, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { getTaskNames, runTask } from '@/api/tasks';

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmitted: (traceId: string) => void;
}

interface FormValues {
  task_name: string;
  date_string?: Dayjs;
  extra_json?: string;
}

export function TaskSubmitForm({ open, onClose, onSubmitted }: Props) {
  const [form] = Form.useForm<FormValues>();
  const [taskOptions, setTaskOptions] = useState<{ value: string; label: string }[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ date_string: dayjs() });
      // 拉取已注册任务列表
      setLoadingOptions(true);
      getTaskNames()
        .then((names) => {
          setTaskOptions(names.map((n) => ({ value: n, label: n })));
        })
        .catch(() => {
          message.error('获取任务列表失败');
        })
        .finally(() => setLoadingOptions(false));
    }
  }, [open, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    let extra: Record<string, unknown> = {};
    if (values.extra_json?.trim()) {
      try {
        extra = JSON.parse(values.extra_json);
      } catch {
        message.error('额外参数不是合法的 JSON');
        return;
      }
    }
    try {
      const res = await runTask({
        task_name: values.task_name.trim(),
        date_string: values.date_string?.format('YYYY-MM-DD'),
        ...extra,
      });
      message.success(`任务已提交: ${res.trace_id}`);
      onSubmitted(res.trace_id);
      onClose();
    } catch {
      // 拦截器已经提示
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="提交任务"
      width={520}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" onClick={handleSubmit}>
            提交
          </Button>
        </Space>
      }
    >
      <Form<FormValues> form={form} layout="vertical" requiredMark="optional">
        <Form.Item
          name="task_name"
          label="task_name"
          rules={[{ required: true, message: '必填' }]}
          tooltip="从已注册的任务处理器中选择"
        >
          <Select
            placeholder="选择任务…"
            showSearch
            optionFilterProp="label"
            options={taskOptions}
            loading={loadingOptions}
            autoFocus
            notFoundContent={loadingOptions ? '加载中…' : '暂无已注册任务'}
          />
        </Form.Item>
        <Form.Item name="date_string" label="业务日期" tooltip="不填则取后端服务器当前日期">
          <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item
          name="extra_json"
          label="额外参数 (JSON)"
          tooltip="会被原样合并到 request body，传递给 task handler"
        >
          <Input.TextArea
            rows={6}
            placeholder='{"window_minutes": 30}'
            styles={{ textarea: { fontFamily: 'ui-monospace, SFMono-Regular, monospace' } }}
          />
        </Form.Item>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          提交后会立即返回 trace_id 并跳到任务详情页，可在那里观察 Agent 流程追溯。
        </Typography.Paragraph>
      </Form>
    </Drawer>
  );
}
