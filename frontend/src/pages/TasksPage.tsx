import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, DatePicker, Form, Input, message, Segmented, Select, Space } from 'antd';
import { PlusOutlined, ReloadOutlined, FilterOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';
import { useNavigate, useSearchParams } from 'react-router-dom';
import dayjs from 'dayjs';
import { TaskListTable } from '@/components/task/TaskListTable';
import { TaskSubmitForm } from '@/components/task/TaskSubmitForm';
import { useTaskStore } from '@/stores/taskStore';
import { useAuthStore } from '@/stores/authStore';
import { cancelTask, cancelAdminTask } from '@/api/tasks';
import { TaskStatus, TASK_STATUS_LABEL_KEYS } from '@/api/types';

const STATUS_VALUES: TaskStatus[] = [
  TaskStatus.INIT,
  TaskStatus.PROCESSING,
  TaskStatus.SUCCESS,
  TaskStatus.CANCEL_REQUESTED,
  TaskStatus.CANCELLED,
  TaskStatus.FAILED,
];

interface FilterValues {
  status?: TaskStatus[];
  task_name?: string;
  date?: dayjs.Dayjs;
}

export function TasksPage() {
  const { t } = useTranslation('tasks');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { items, total, loading, params, adminMode, fetch, setAdminMode } = useTaskStore();
  const account = useAuthStore((s) => s.account);
  const isAdmin = account?.role === 'admin';
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [filterForm] = Form.useForm<FilterValues>();

  const statusOptions = useMemo(
    () => STATUS_VALUES.map((s) => ({ value: s, label: t(TASK_STATUS_LABEL_KEYS[s]) })),
    [t],
  );

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
        const res = adminMode
          ? await cancelAdminTask(traceId)
          : await cancelTask({ trace_id: traceId });
        if (res.code === 0) {
          message.success(t('cancelRequested'));
        } else {
          message.warning(res.message || t('taskNotFoundOrEnded'));
        }
        await fetch();
      } catch {
        // 拦截器已提示
      }
    },
    [fetch, adminMode, t]
  );

  return (
    <PageShell>
      <PageHero
        title={t('pageTitle')}
        subtitle={t('pageSubtitle')}
        icon={<UnorderedListOutlined />}
        gradient="purple"
      />

      <PageCard
        title={
          <PageCardTitle
            icon={
              <PageCardIcon color="#3A506B" bg="rgba(58,80,107,0.12)">
                <FilterOutlined />
              </PageCardIcon>
            }
          >
            {t('filter')}
          </PageCardTitle>
        }
        styles={{ body: { padding: '18px 22px' } }}
        style={{ marginBottom: 20 }}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {isAdmin && (
            <Segmented
              value={adminMode ? 'all' : 'mine'}
              onChange={(val) => {
                setAdminMode(val === 'all');
                filterForm.resetFields();
              }}
              options={[
                { label: t('myTasks'), value: 'mine' },
                { label: t('allUsers'), value: 'all' },
              ]}
            />
          )}
          <Form<FilterValues> form={filterForm} layout="inline" onFinish={applyFilter}>
            <Form.Item name="status" label={t('statusLabel')}>
              <Select
                mode="multiple"
                placeholder={t('statusAll')}
                style={{ minWidth: 220 }}
                options={statusOptions}
                allowClear
                maxTagCount="responsive"
              />
            </Form.Item>
            <Form.Item name="task_name" label={t('taskNameLabel')}>
              <Input placeholder={t('taskNamePlaceholder')} allowClear style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="date" label={t('bizDateLabel')}>
              <DatePicker format="YYYY-MM-DD" />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" icon={<FilterOutlined />} htmlType="submit">
                  {t('filter')}
                </Button>
                <Button onClick={resetFilter}>{t('reset')}</Button>
                <Button icon={<ReloadOutlined />} onClick={() => fetch()}>
                  {t('refresh')}
                </Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setDrawerOpen(true)}>
                  {t('submitTask')}
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Space>
      </PageCard>

      <PageCard table styles={{ body: { padding: 0 } }}>
        <TaskListTable
          items={items}
          total={total}
          page={params.page ?? 1}
          pageSize={params.page_size ?? 20}
          loading={loading}
          onPageChange={(page, page_size) => fetch({ page, page_size })}
          onCancel={handleCancel}
        />
      </PageCard>

      <TaskSubmitForm
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSubmitted={(traceId) => navigate(`/tasks/${encodeURIComponent(traceId)}`)}
      />
    </PageShell>
  );
}
