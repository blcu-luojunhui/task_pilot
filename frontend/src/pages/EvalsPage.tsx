import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Col, Row, Select, Statistic, Table, Tag, Typography, theme } from 'antd';
import { ExperimentOutlined, BarChartOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { getEvalReport, listEvalReports } from '@/api/eval';
import type { EvalCase } from '@/api/eval';
import { evalKeys } from '@/api/queryKeys';
import { PageShell } from '@/components/common/PageShell';
import { PageHero } from '@/components/common/PageHero';
import { PageCard, PageCardIcon, PageCardTitle } from '@/components/common/PageCard';

export function EvalsPage() {
  const { token } = theme.useToken();
  const { t } = useTranslation('evals');

  const { data: listData, isLoading: listLoading } = useQuery({
    queryKey: evalKeys.reports(),
    queryFn: listEvalReports,
  });

  const reports = listData?.items ?? [];
  const [reportId, setReportId] = useState<string | undefined>(reports[0]?.report_id);

  const activeId = reportId ?? reports[0]?.report_id;

  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: evalKeys.report(activeId ?? ''),
    queryFn: () => getEvalReport(activeId!),
    enabled: Boolean(activeId),
  });

  const columns = useMemo(
    () => [
      { title: t('table.goal'), dataIndex: 'goal', ellipsis: true },
      {
        title: t('table.success'),
        dataIndex: 'success',
        width: 90,
        render: (v: boolean) => (
          <Tag color={v ? 'success' : 'error'}>{v ? t('table.pass') : t('table.fail')}</Tag>
        ),
      },
      { title: t('table.steps'), dataIndex: 'steps', width: 80 },
      { title: t('table.tokens'), dataIndex: 'tokens', width: 90 },
      {
        title: t('table.judge'),
        dataIndex: 'judge_score',
        width: 90,
        render: (v: number | null) => (v != null ? v.toFixed(2) : '—'),
      },
      {
        title: t('table.trace'),
        dataIndex: 'trace_id',
        width: 140,
        render: (traceId: string | null) =>
          traceId ? (
            <Link to={`/tasks/${encodeURIComponent(traceId)}`}>{t('table.viewTrace')}</Link>
          ) : (
            '—'
          ),
      },
    ],
    [t],
  );

  const summary = report?.summary;

  return (
    <PageShell>
      <PageHero
        title={t('title')}
        subtitle={t('subtitle')}
        icon={<ExperimentOutlined />}
        gradient="green"
        extra={
          <Select
            style={{ minWidth: 260 }}
            loading={listLoading}
            value={activeId}
            onChange={setReportId}
            options={reports.map((r) => ({
              value: r.report_id,
              label: `${r.name} (${(r.success_rate * 100).toFixed(0)}%)`,
            }))}
          />
        }
      />

      {summary && (
        <Row gutter={[20, 20]} style={{ marginBottom: 20 }}>
          <Col xs={12} md={6}>
            <PageCard styles={{ body: { padding: '16px 20px' } }}>
              <Statistic
                title={t('metrics.successRate')}
                value={summary.success_rate * 100}
                precision={1}
                suffix="%"
                valueStyle={{ fontWeight: 600 }}
              />
            </PageCard>
          </Col>
          <Col xs={12} md={6}>
            <PageCard styles={{ body: { padding: '16px 20px' } }}>
              <Statistic title={t('metrics.avgSteps')} value={summary.avg_steps} precision={1} valueStyle={{ fontWeight: 600 }} />
            </PageCard>
          </Col>
          <Col xs={12} md={6}>
            <PageCard styles={{ body: { padding: '16px 20px' } }}>
              <Statistic title={t('metrics.avgTokens')} value={summary.avg_tokens} valueStyle={{ fontWeight: 600 }} />
            </PageCard>
          </Col>
          <Col xs={12} md={6}>
            <PageCard styles={{ body: { padding: '16px 20px' } }}>
              <Statistic
                title={t('metrics.toolErrorRate')}
                value={summary.tool_error_rate * 100}
                precision={1}
                suffix="%"
                valueStyle={{ fontWeight: 600 }}
              />
            </PageCard>
          </Col>
        </Row>
      )}

      {report?.trend && report.trend.length > 0 && (
        <PageCard
          style={{ marginBottom: 20 }}
          title={
            <PageCardTitle
              icon={
                <PageCardIcon color={token.colorPrimary} bg={token.colorPrimaryBg}>
                  <BarChartOutlined />
                </PageCardIcon>
              }
            >
              {t('trendTitle')}
            </PageCardTitle>
          }
          styles={{ body: { padding: '16px 20px' } }}
        >
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={report.trend}>
                <XAxis dataKey="date" stroke={token.colorTextSecondary} />
                <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <Tooltip
                  formatter={(v) =>
                    typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : String(v ?? '')
                  }
                />
                <Line
                  type="monotone"
                  dataKey="success_rate"
                  stroke={token.colorPrimary}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </PageCard>
      )}

      <PageCard
        table
        title={
          <PageCardTitle
            icon={
              <PageCardIcon color="#5856d6" bg="rgba(88,86,214,0.12)">
                <UnorderedListOutlined />
              </PageCardIcon>
            }
          >
            {t('casesTitle')}
          </PageCardTitle>
        }
        styles={{ body: { padding: 0 } }}
      >
        <Table<EvalCase>
          rowKey="case_id"
          size="middle"
          loading={reportLoading}
          dataSource={report?.cases ?? []}
          columns={columns}
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (row) => (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                {row.judge_reason || t('table.noReason')}
              </Typography.Paragraph>
            ),
          }}
        />
      </PageCard>
    </PageShell>
  );
}
