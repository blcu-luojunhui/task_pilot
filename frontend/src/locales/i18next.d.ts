import 'react-i18next';
import type enCommon from './en/common.json';
import type enAuth from './en/auth.json';
import type enDashboard from './en/dashboard.json';
import type enTasks from './en/tasks.json';
import type enChat from './en/chat.json';
import type enAccount from './en/account.json';
import type enSkills from './en/skills.json';
import type enRuns from './en/runs.json';
import type enRunTask from './en/runTask.json';
import type enSystem from './en/system.json';
import type enTrace from './en/trace.json';
import type enReplay from './en/replay.json';

declare module 'react-i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: typeof enCommon;
      auth: typeof enAuth;
      dashboard: typeof enDashboard;
      tasks: typeof enTasks;
      chat: typeof enChat;
      account: typeof enAccount;
      skills: typeof enSkills;
      runs: typeof enRuns;
      runTask: typeof enRunTask;
      system: typeof enSystem;
      trace: typeof enTrace;
      replay: typeof enReplay;
    };
  }
}
