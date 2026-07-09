export const chatKeys = {
  all: ['chat'] as const,
  conversations: () => [...chatKeys.all, 'conversations'] as const,
  conversation: (id: string) => [...chatKeys.all, 'conversation', id] as const,
};

export const evalKeys = {
  all: ['evals'] as const,
  reports: () => [...evalKeys.all, 'reports'] as const,
  report: (id: string) => [...evalKeys.all, 'report', id] as const,
};
