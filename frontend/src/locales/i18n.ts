import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { useLocaleStore } from '@/stores/localeStore';

import enCommon from './en/common.json';
import enAuth from './en/auth.json';
import enDashboard from './en/dashboard.json';
import enTasks from './en/tasks.json';
import enChat from './en/chat.json';
import enAccount from './en/account.json';
import enSkills from './en/skills.json';
import enRuns from './en/runs.json';
import enRunTask from './en/runTask.json';
import enSystem from './en/system.json';
import enTrace from './en/trace.json';
import enReplay from './en/replay.json';

import zhCommon from './zh/common.json';
import zhAuth from './zh/auth.json';
import zhDashboard from './zh/dashboard.json';
import zhTasks from './zh/tasks.json';
import zhChat from './zh/chat.json';
import zhAccount from './zh/account.json';
import zhSkills from './zh/skills.json';
import zhRuns from './zh/runs.json';
import zhRunTask from './zh/runTask.json';
import zhSystem from './zh/system.json';
import zhTrace from './zh/trace.json';
import zhReplay from './zh/replay.json';

const resources = {
  en: {
    common: enCommon,
    auth: enAuth,
    dashboard: enDashboard,
    tasks: enTasks,
    chat: enChat,
    account: enAccount,
    skills: enSkills,
    runs: enRuns,
    runTask: enRunTask,
    system: enSystem,
    trace: enTrace,
    replay: enReplay,
  },
  zh: {
    common: zhCommon,
    auth: zhAuth,
    dashboard: zhDashboard,
    tasks: zhTasks,
    chat: zhChat,
    account: zhAccount,
    skills: zhSkills,
    runs: zhRuns,
    runTask: zhRunTask,
    system: zhSystem,
    trace: zhTrace,
    replay: zhReplay,
  },
};

const storedLocale = useLocaleStore.getState().locale;

i18n.use(initReactI18next).init({
  resources,
  lng: storedLocale,
  fallbackLng: 'zh',
  defaultNS: 'common',
  interpolation: { escapeValue: false },
  returnObjects: true,
});

useLocaleStore.subscribe((state) => {
  if (i18n.language !== state.locale) {
    i18n.changeLanguage(state.locale);
  }
});

export default i18n;
