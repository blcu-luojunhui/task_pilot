import { Tabs } from 'antd';
import {
  OrderedListOutlined,
  ApartmentOutlined,
  MessageOutlined,
  BarChartOutlined,
  CodeOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import type { TraceEvent } from '@/api/types';
import { TimelineView } from './TimelineView';
import { StepTreeView } from './StepTreeView';
import { TranscriptView } from './TranscriptView';
import { StatsView } from './StatsView';
import { PromptInspector } from './PromptInspector';
import { DAGView } from './DAGView';

const TAB_ITEMS = [
  {
    key: 'timeline',
    label: 'Timeline',
    icon: <OrderedListOutlined />,
    render: (events: TraceEvent[]) => <TimelineView events={events} />,
  },
  {
    key: 'tree',
    label: 'Step Tree',
    icon: <ApartmentOutlined />,
    render: (events: TraceEvent[]) => <StepTreeView events={events} />,
  },
  {
    key: 'transcript',
    label: 'Transcript',
    icon: <MessageOutlined />,
    render: (events: TraceEvent[]) => <TranscriptView events={events} />,
  },
  {
    key: 'stats',
    label: 'Stats',
    icon: <BarChartOutlined />,
    render: (events: TraceEvent[]) => <StatsView events={events} />,
  },
  {
    key: 'prompt',
    label: 'Prompt',
    icon: <CodeOutlined />,
    render: (events: TraceEvent[]) => <PromptInspector events={events} />,
  },
  {
    key: 'dag',
    label: 'DAG',
    icon: <ShareAltOutlined />,
    render: (events: TraceEvent[]) => <DAGView events={events} />,
  },
];

export function TraceView({ events }: { events: TraceEvent[] }) {
  return (
    <Tabs
      defaultActiveKey="timeline"
      items={TAB_ITEMS.map((tab) => ({
        key: tab.key,
        label: (
          <span>
            {tab.icon} {tab.label}
          </span>
        ),
        children: tab.render(events),
      }))}
    />
  );
}
