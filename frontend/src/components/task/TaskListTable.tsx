import { useCallback, useMemo, useState } from 'react';
import { Button, Popconfirm, Space, Table, Tooltip, Typography } from 'antd';
import type { TableColumnsType, TablePaginationConfig } from 'antd';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Resizable } from 'react-resizable';
import type { ResizeCallbackData } from 'react-resizable';
import { TaskStatus, type TaskSummary } from '@/api/types';
import { TaskStatusTag } from './TaskStatusTag';
import { formatDuration, formatTimestamp, truncateTraceId } from '@/utils/format';
import './TaskListTable.css';

interface Props {
  items: TaskSummary[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onCancel: (traceId: string) => void;
}

function ResizableTitle(
  props: React.HTMLAttributes<HTMLElement> & {
    onResize: (e: React.SyntheticEvent, data: ResizeCallbackData) => void;
    width?: number;
  },
) {
  const { onResize, width, ...restProps } = props;

  if (width == null) {
    return <th {...restProps} />;
  }

  return (
    <Resizable
      width={width}
      height={0}
      axis="x"
      handleSize={[20, 20]}
      lockAspectRatio={false}
      minConstraints={[60, 0]}
      maxConstraints={[600, 0]}
      resizeHandles={['e']}
      transformScale={1}
      handle={
        <span
          className="react-resizable-handle"
          onClick={(e) => e.stopPropagation()}
        />
      }
      onResize={onResize}
      draggableOpts={{ enableUserSelectHack: false }}
    >
      <th {...restProps} />
    </Resizable>
  );
}

const COLUMN_DEFAULTS: Record<string, number> = {
  task_status: 110,
  trace_id: 240,
  task_name: 200,
  date_string: 120,
  start_timestamp: 180,
  duration: 110,
  actions: 160,
};

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
  const { t } = useTranslation('tasks');
  const [colWidths, setColWidths] = useState<Record<string, number>>({});

  const handleResize = useCallback(
    (key: string) =>
      (_e: React.SyntheticEvent, { size }: ResizeCallbackData) => {
        setColWidths((prev) => ({ ...prev, [key]: size.width }));
      },
    [],
  );

  const baseColumns: TableColumnsType<TaskSummary> = useMemo(
    () => [
      {
        title: t('tableStatus'),
        dataIndex: 'task_status',
        key: 'task_status',
        width: COLUMN_DEFAULTS.task_status,
        render: (status: TaskStatus) => <TaskStatusTag status={status} />,
      },
      {
        title: t('tableTraceId'),
        dataIndex: 'trace_id',
        key: 'trace_id',
        width: COLUMN_DEFAULTS.trace_id,
        ellipsis: true,
        render: (traceId: string) => (
          <Tooltip title={traceId}>
            <Typography.Link
              onClick={() => navigate(`/tasks/${encodeURIComponent(traceId)}`)}
              style={{ fontSize: 12 }}
            >
              <code style={{ fontSize: 12 }}>{truncateTraceId(traceId)}</code>
            </Typography.Link>
          </Tooltip>
        ),
      },
      {
        title: t('tableTaskName'),
        dataIndex: 'task_name',
        key: 'task_name',
        width: COLUMN_DEFAULTS.task_name,
        ellipsis: true,
      },
      {
        title: t('tableBizDate'),
        dataIndex: 'date_string',
        key: 'date_string',
        width: COLUMN_DEFAULTS.date_string,
      },
      {
        title: t('tableStartTime'),
        dataIndex: 'start_timestamp',
        key: 'start_timestamp',
        width: COLUMN_DEFAULTS.start_timestamp,
        render: (ts: number) => formatTimestamp(ts),
      },
      {
        title: t('tableDuration'),
        key: 'duration',
        width: COLUMN_DEFAULTS.duration,
        render: (_, record) => formatDuration(record.start_timestamp, record.finish_timestamp),
      },
      {
        title: t('tableActions'),
        key: 'actions',
        width: COLUMN_DEFAULTS.actions,
        fixed: 'right' as const,
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
                {t('tableView')}
              </Button>
              <Popconfirm
                title={t('cancelConfirmTitle')}
                description={t('cancelConfirmDesc')}
                okText={t('cancelConfirmOk')}
                cancelText={t('cancelConfirmCancel')}
                disabled={!cancellable}
                onConfirm={() => onCancel(record.trace_id)}
              >
                <Button type="link" size="small" danger disabled={!cancellable}>
                  {t('cancel')}
                </Button>
              </Popconfirm>
            </Space>
          );
        },
      },
    ],
    [t, navigate, onCancel],
  );

  const columns = useMemo(
    () =>
      baseColumns.map((col) => ({
        ...col,
        width: colWidths[col.key as string] ?? col.width,
        onHeaderCell: (column: typeof col) => ({
          width: colWidths[column.key as string] ?? column.width,
          onResize: handleResize(column.key as string),
        }),
      })),
    [baseColumns, colWidths, handleResize],
  );

  const scrollX = useMemo(
    () =>
      Object.values({ ...COLUMN_DEFAULTS, ...colWidths }).reduce((s, w) => s + w, 0) + 40,
    [colWidths],
  );

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (totalCount) => t('totalCount', { count: totalCount }),
    onChange: onPageChange,
  };

  return (
    <Table<TaskSummary>
      rowKey="trace_id"
      loading={loading}
      columns={columns}
      dataSource={items}
      pagination={pagination}
      scroll={{ x: scrollX }}
      size="middle"
      components={{
        header: {
          cell: ResizableTitle,
        },
      }}
    />
  );
}
