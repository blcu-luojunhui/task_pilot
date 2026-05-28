import { useMemo } from 'react';
import { Col, Empty, Row, Statistic, Typography } from 'antd';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
  Legend,
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { TraceEvent } from '@/api/types';

const PIE_COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2', '#eb2f96', '#fa8c16'];

interface StepTiming {
  step: number;
  thinkMs: number;
  actMs: number;
}

interface TokenPoint {
  step: number;
  prompt: number;
  completion: number;
  total: number;
}

function parseTimestamps(events: TraceEvent[]): StepTiming[] {
  const byStep = new Map<number, { thinkStart?: string; thinkEnd?: string; actStart?: string; actEnd?: string }>();

  for (const evt of events) {
    if (evt.step == null) continue;
    const bucket = byStep.get(evt.step) || {};
    if (evt.type === 'think_start') bucket.thinkStart = evt.timestamp;
    if (evt.type === 'think_end') bucket.thinkEnd = evt.timestamp;
    if (evt.type === 'act_start') bucket.actStart = evt.timestamp;
    if (evt.type === 'act_end') bucket.actEnd = evt.timestamp;
    byStep.set(evt.step, bucket);
  }

  const timings: StepTiming[] = [];
  for (const [step, t] of [...byStep.entries()].sort((a, b) => a[0] - b[0])) {
    const thinkStart = t.thinkStart ? new Date(t.thinkStart).getTime() : 0;
    const thinkEnd = t.thinkEnd ? new Date(t.thinkEnd).getTime() : 0;
    const actStart = t.actStart ? new Date(t.actStart).getTime() : 0;
    const actEnd = t.actEnd ? new Date(t.actEnd).getTime() : 0;

    timings.push({
      step,
      thinkMs: Math.max(0, thinkEnd - thinkStart),
      actMs: Math.max(0, actEnd - actStart),
    });
  }
  return timings;
}

function parseTokens(events: TraceEvent[]): TokenPoint[] {
  const points: TokenPoint[] = [];
  const cumulative = { prompt: 0, completion: 0, total: 0 };

  for (const evt of events) {
    const data = evt.data as Record<string, unknown>;

    // 从 assistant_message 或顶层提取 token 数据
    let usage: { prompt?: number; completion?: number; total?: number } | undefined;

    if (evt.type === 'think_end') {
      const msg = data.assistant_message as Record<string, unknown> | undefined;
      usage = (msg?._usage || data._usage) as { prompt?: number; completion?: number; total?: number } | undefined;
    }

    if (usage) {
      cumulative.prompt += usage.prompt ?? 0;
      cumulative.completion += usage.completion ?? 0;
      cumulative.total += usage.total ?? 0;
    }

    points.push({
      step: evt.step ?? points.length,
      prompt: cumulative.prompt,
      completion: cumulative.completion,
      total: cumulative.total,
    });
  }

  return points;
}

interface ToolCount {
  name: string;
  count: number;
}

function parseToolCounts(events: TraceEvent[]): ToolCount[] {
  const counts = new Map<string, number>();
  for (const evt of events) {
    if (evt.type === 'act_start') {
      const calls = (evt.data as { tool_calls?: Array<{ name?: string }> }).tool_calls;
      if (calls) {
        for (const tc of calls) {
          const name = tc.name || 'unknown';
          counts.set(name, (counts.get(name) || 0) + 1);
        }
      }
    }
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function StatsView({ events }: { events: TraceEvent[] }) {
  const timings = useMemo(() => parseTimestamps(events), [events]);
  const tokens = useMemo(() => parseTokens(events), [events]);
  const toolCounts = useMemo(() => parseToolCounts(events), [events]);

  if (events.length === 0) {
    return <Empty description="无统计数据" />;
  }

  const totalThink = timings.reduce((s, t) => s + t.thinkMs, 0);
  const totalAct = timings.reduce((s, t) => s + t.actMs, 0);
  const lastToken = tokens[tokens.length - 1];

  return (
    <div style={{ padding: '8px 0' }}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Statistic title="总思考耗时" value={totalThink} suffix="ms" precision={0} />
        </Col>
        <Col span={6}>
          <Statistic title="总执行耗时" value={totalAct} suffix="ms" precision={0} />
        </Col>
        <Col span={6}>
          <Statistic
            title="Token 用量"
            value={lastToken?.total ?? 0}
            suffix={`tokens (prompt: ${lastToken?.prompt ?? 0} / completion: ${lastToken?.completion ?? 0})`}
          />
        </Col>
        <Col span={6}>
          <Statistic title="工具调用" value={toolCounts.reduce((s, t) => s + t.count, 0)} suffix="次" />
        </Col>
      </Row>

      {timings.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <Typography.Title level={5}>每步耗时 (ms)</Typography.Title>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={timings}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="step" label={{ value: 'Step', position: 'insideBottom', offset: -5 }} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="thinkMs" name="Think" fill="#8884d8" stackId="a" />
              <Bar dataKey="actMs" name="Act" fill="#82ca9d" stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {tokens.length > 1 && (
        <div style={{ marginBottom: 24 }}>
          <Typography.Title level={5}>Token 累积曲线</Typography.Title>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={tokens}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="step" label={{ value: 'Step', position: 'insideBottom', offset: -5 }} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="prompt" name="Prompt" stroke="#8884d8" />
              <Line type="monotone" dataKey="completion" name="Completion" stroke="#82ca9d" />
              <Line type="monotone" dataKey="total" name="Total" stroke="#ff7300" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {toolCounts.length > 0 && (
        <div>
          <Typography.Title level={5}>工具调用分布</Typography.Title>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={toolCounts}
                dataKey="count"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={({ name, value }) => `${name} (${value})`}
              >
                {toolCounts.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
