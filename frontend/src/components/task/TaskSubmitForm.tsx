import { useEffect, useState } from 'react';
import { Button, DatePicker, Drawer, Form, Input, message, Select, Space, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { getTaskNames, runTask } from '@/api/tasks';
import { FONT_MONO } from '@/utils/fonts';

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
  const { t } = useTranslation('tasks');

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({ date_string: dayjs() });
      setLoadingOptions(true);
      getTaskNames()
        .then((names) => {
          setTaskOptions(names.map((n) => ({ value: n, label: n })));
        })
        .catch(() => {
          message.error(t('loadTaskNamesFailed'));
        })
        .finally(() => setLoadingOptions(false));
    }
  }, [open, form, t]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    let extra: Record<string, unknown> = {};
    if (values.extra_json?.trim()) {
      try {
        extra = JSON.parse(values.extra_json);
      } catch {
        message.error(t('invalidJson'));
        return;
      }
    }
    try {
      const res = await runTask({
        task_name: values.task_name.trim(),
        date_string: values.date_string?.format('YYYY-MM-DD'),
        ...extra,
      });
      message.success(t('submitSuccess', { traceId: res.trace_id }));
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
      title={t('formTitle')}
      width={520}
      destroyOnClose
      extra={
        <Space>
          <Button onClick={onClose}>{t('formCancel')}</Button>
          <Button type="primary" onClick={handleSubmit}>
            {t('formSubmit')}
          </Button>
        </Space>
      }
    >
      <Form<FormValues> form={form} layout="vertical" requiredMark="optional">
        <Form.Item
          name="task_name"
          label="task_name"
          rules={[{ required: true, message: t('formRequired') }]}
          tooltip={t('formTaskNameTooltip')}
        >
          <Select
            placeholder={t('formTaskNamePlaceholder')}
            showSearch
            optionFilterProp="label"
            options={taskOptions}
            loading={loadingOptions}
            autoFocus
            notFoundContent={loadingOptions ? t('formTaskNameLoading') : t('formTaskNameNoData')}
          />
        </Form.Item>
        <Form.Item name="date_string" label={t('formBizDate')} tooltip={t('formBizDateTooltip')}>
          <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item
          name="extra_json"
          label={t('formExtraJson')}
          tooltip={t('formExtraJsonTooltip')}
        >
          <Input.TextArea
            rows={6}
            placeholder='{"window_minutes": 30}'
            styles={{ textarea: { fontFamily: FONT_MONO } }}
          />
        </Form.Item>
        <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
          {t('formSubmitHint')}
        </Typography.Paragraph>
      </Form>
    </Drawer>
  );
}
