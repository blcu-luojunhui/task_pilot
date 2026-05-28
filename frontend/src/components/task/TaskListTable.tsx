import { Button, Popconfirm, Space, Table, Tooltip, Typography } from 'antd';
import type { TableColumnsType, TablePaginationConfig } from 'antd';
import { useNavigate } from 'react-router-dom';
import { TaskStatus, type TaskSummary } from '@/api/types';
import { TaskStatusTag } from './TaskStatusTag';
import { formatDuration, formatTimestamp, truncateTraceId } from '@/utils/format';

interface Props {
  items: TaskSummary[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onCancel: (traceId: string) => void;
}

export function TaskListTable({
  items,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onCancel,
}: Props) {
  const navigate = useNavigate();

  const columns: TableColumnsType<TaskSummary> = [
    {
      title: '状态',
      dataIndex: 'task_status',
      key: 'task_status',
      width: 96,
      render: (status: TaskStatus) => <TaskStatusTag status={status} />,
    },
    {
      title: 'trace_id',
      dataIndex: 'trace_id',
      key: 'trace_id',
      width: 240,
      render: (traceId: string) => (
        <Tooltip title={traceId}>
          <Typography.Link onClick={() => navigate(`/tasks/${encodeURIComponent(traceId)}`)}>
            <code style={{ fontSize: 12 }}>{truncateTraceId(traceId)}</code>
          </Typography.Link>
        </Tooltip>
      ),
    },
    {
      title: '任务名',
      dataIndex: 'task_name',
      key: 'task_name',
      ellipsis: true,
    },
    {
      title: '业务日期',
      dataIndex: 'date_string',
      key: 'date_string',
      width: 120,
    },
    {
      title: '开始时间',
      dataIndex: 'start_timestamp',
      key: 'start_timestamp',
      width: 180,
      render: (ts: number) => formatTimestamp(ts),
    },
    {
      title: '耗时',
      key: 'duration',
      width: 110,
      render: (_, record) => formatDuration(record.start_timestamp, record.finish_timestamp),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      fixed: 'right',
      render: (_, record) => {
        const cancellable =
          record.task_status === TaskStatus.PROCESSING ||
          record.task_status === TaskStatus.INIT;
        return (
          <Space size="small">
            <Button
              type="link"
              size="small"
              onClick={() => navigate(`/tasks/${encodeURIComponent(record.trace_id)}`)}
            >
              查看
            </Button>
            <Popconfirm
              title="确认取消该任务？"
              description="后端会写入 CANCEL_REQUESTED，由生命周期管理器协作取消。"
              okText="取消任务"
              cancelText="放弃"
              disabled={!cancellable}
              onConfirm={() => onCancel(record.trace_id)}
            >
              <Button type="link" size="small" danger disabled={!cancellable}>
                取消
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (t) => `共 ${t} 条`,
    onChange: onPageChange,
  };

  return (
    <Table<TaskSummary>
      rowKey="trace_id"
      loading={loading}
      columns={columns}
      dataSource={items}
      pagination={pagination}
      scroll={{ x: 1100 }}
      size="middle"
    />
  );
}
