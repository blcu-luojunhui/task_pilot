import { useCallback, useSyncExternalStore } from 'react';

const STORAGE_KEY = 'taskpilot-dark-mode';

function getSnapshot(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

function subscribe(callback: () => void) {
  const handler = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback();
  };
  window.addEventListener('storage', handler);
  return () => window.removeEventListener('storage', handler);
}

function setDarkMode(v: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, String(v));
  } catch {
    // localStorage 不可用时静默降级
  }
  // 手动触发 storage 事件不会冒泡到同 window，需要手动 dispatch
  window.dispatchEvent(
    new StorageEvent('storage', { key: STORAGE_KEY, newValue: String(v) })
  );
}

export function useDarkMode(): [boolean, (v: boolean) => void] {
  const isDark = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const toggle = useCallback((v: boolean) => setDarkMode(v), []);
  return [isDark, toggle];
}
