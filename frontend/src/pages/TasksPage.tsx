import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, DatePicker, Form, Input, message, Select, Space } from 'antd';
import { PlusOutlined, ReloadOutlined, FilterOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import dayjs from 'dayjs';
import { TaskListTable } from '@/components/task/TaskListTable';
import { TaskSubmitForm } from '@/components/task/TaskSubmitForm';
import { useTaskStore } from '@/stores/taskStore';
import { cancelTask } from '@/api/tasks';
import { TaskStatus, TASK_STATUS_LABEL } from '@/api/types';

const STATUS_OPTIONS = (
  [
    TaskStatus.INIT,
    TaskStatus.PROCESSING,
    TaskStatus.SUCCESS,
    TaskStatus.CANCEL_REQUESTED,
    TaskStatus.CANCELLED,
    TaskStatus.FAILED,
  ] as TaskStatus[]
).map((s) => ({ value: s, label: TASK_STATUS_LABEL[s] }));

interface FilterValues {
  status?: TaskStatus[];
  task_name?: string;
  date?: dayjs.Dayjs;
}

export function TasksPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { items, total, loading, params, fetch } = useTaskStore();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [filterForm] = Form.useForm<FilterValues>();

  /** 首次加载 + URL 带的 task_name 预填 */
  useEffect(() => {
    const taskName = searchParams.get('task_name') ?? undefined;
    if (taskName) {
      filterForm.setFieldsValue({ task_name: taskName });
    }
    fetch({ page: 1, task_name: taskName });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 列表中有执行中/取消中任务时，每 5 秒轮询刷新 */
  const fetchRef = useRef(fetch);
  fetchRef.current = fetch;
  useEffect(() => {
    const hasLive = items.some(
      (t) =>
        t.task_status === TaskStatus.PROCESSING ||
        t.task_status === TaskStatus.CANCEL_REQUESTED
    );
    if (!hasLive) return;
    const id = setInterval(() => fetchRef.current(), 5000);
    return () => clearInterval(id);
  }, [items]);

  const applyFilter = useCallback(() => {
    const v = filterForm.getFieldsValue();
    fetch({
      page: 1,
      status: v.status,
      task_name: v.task_name?.trim() || undefined,
      date: v.date ? v.date.format('YYYY-MM-DD') : undefined,
    });
  }, [filterForm, fetch]);

  const resetFilter = useCallback(() => {
    filterForm.resetFields();
    fetch({ page: 1, status: undefined, task_name: undefined, date: undefined });
  }, [filterForm, fetch]);

  const handleCancel = useCallback(
    async (traceId: string) => {
      try {
        const res = await cancelTask({ trace_id: traceId });
        if (res.code === 0) {
          message.success('已请求取消');
        } else {
          message.warning(res.message || '任务不存在或已结束');
        }
        await fetch();
      } catch {
        // 拦截器已提示
      }
    },
    [fetch]
  );

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card variant="borderless">
        <Form<FilterValues> form={filterForm} layout="inline" onFinish={applyFilter}>
          <Form.Item name="status" label="状态">
            <Select
              mode="multiple"
              placeholder="全部"
              style={{ minWidth: 220 }}
              options={STATUS_OPTIONS}
              allowClear
              maxTagCount="responsive"
            />
          </Form.Item>
          <Form.Item name="task_name" label="任务名">
            <Input placeholder="模糊匹配" allowClear style={{ width: 200 }} />
          </Form.Item>
          <Form.Item name="date" label="业务日期">
            <DatePicker format="YYYY-MM-DD" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<FilterOutlined />} htmlType="submit">
                筛选
              </Button>
              <Button onClick={resetFilter}>重置</Button>
              <Button icon={<ReloadOutlined />} onClick={() => fetch()}>
                刷新
              </Button>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setDrawerOpen(true)}
              >
                提交任务
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card variant="borderless" styles={{ body: { padding: 0 } }}>
        <TaskListTable
          items={items}
          total={total}
          page={params.page ?? 1}
          pageSize={params.page_size ?? 20}
          loading={loading}
          onPageChange={(page, page_size) => fetch({ page, page_size })}
          onCancel={handleCancel}
        />
      </Card>

      <TaskSubmitForm
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSubmitted={(traceId) => navigate(`/tasks/${encodeURIComponent(traceId)}`)}
      />
    </Space>
  );
}
