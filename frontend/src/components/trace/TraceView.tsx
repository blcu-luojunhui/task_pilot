import { lazy, Suspense, useMemo, useState } from 'react';
import { Spin, Tabs } from 'antd';
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
import { TimelineScrubber } from './TimelineScrubber';

const DAGView = lazy(() => import('./DAGView').then((m) => ({ default: m.DAGView })));

function TabFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
      <Spin />
    </div>
  );
}

export function TraceView({ events }: { events: TraceEvent[] }) {
  const [selectedStep, setSelectedStep] = useState<number | null>(null);

  const filteredEvents = useMemo(() => {
    if (selectedStep == null) return events;
    return events.filter((e) => e.step == null || e.step <= selectedStep);
  }, [events, selectedStep]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Tabs
        defaultActiveKey="dag"
        destroyInactiveTabPane
        style={{ flex: 1 }}
        items={[
          {
            key: 'dag',
            label: (
              <span>
                <ShareAltOutlined /> DAG
              </span>
            ),
            children: (
              <Suspense fallback={<TabFallback />}>
                <DAGView
                  events={events}
                  selectedStep={selectedStep}
                  onSelectStep={setSelectedStep}
                />
              </Suspense>
            ),
          },
          {
            key: 'timeline',
            label: (
              <span>
                <OrderedListOutlined /> Timeline
              </span>
            ),
            children: <TimelineView events={filteredEvents} />,
          },
          {
            key: 'tree',
            label: (
              <span>
                <ApartmentOutlined /> Step Tree
              </span>
            ),
            children: <StepTreeView events={filteredEvents} />,
          },
          {
            key: 'transcript',
            label: (
              <span>
                <MessageOutlined /> Transcript
              </span>
            ),
            children: <TranscriptView events={filteredEvents} />,
          },
          {
            key: 'stats',
            label: (
              <span>
                <BarChartOutlined /> Stats
              </span>
            ),
            children: <StatsView events={filteredEvents} />,
          },
          {
            key: 'prompt',
            label: (
              <span>
                <CodeOutlined /> Prompt
              </span>
            ),
            children: <PromptInspector events={filteredEvents} />,
          },
        ]}
      />
      <TimelineScrubber
        events={events}
        selectedStep={selectedStep}
        onStepChange={setSelectedStep}
      />
    </div>
  );
}
