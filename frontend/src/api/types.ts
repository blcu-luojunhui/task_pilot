/**
 * 后端 API 数据契约
 *
 * 字段与 `src/jobs/task_config.py` 的 TaskStatus / `init.sql` 的 task_manager 表
 * 以及 `docs/design/frontend-v1.md` §10 的 API Spec 保持一致。
 */

// ============ 任务状态机 ============

export enum TaskStatus {
  INIT = 0,
  PROCESSING = 1,
  SUCCESS = 2,
  CANCELLED = 3,
  CANCEL_REQUESTED = 4,
  FAILED = 99,
}

export const TASK_STATUS_LABEL_KEYS: Record<TaskStatus, string> = {
  [TaskStatus.INIT]: 'status.init',
  [TaskStatus.PROCESSING]: 'status.processing',
  [TaskStatus.SUCCESS]: 'status.success',
  [TaskStatus.CANCELLED]: 'status.cancelled',
  [TaskStatus.CANCEL_REQUESTED]: 'status.cancelRequested',
  [TaskStatus.FAILED]: 'status.failed',
};

// ============ 通用响应包装 ============

export interface ApiResponse<T> {
  code: number;
  message?: string;
  data: T;
}

// ============ Tasks ============

export interface TaskSummary {
  trace_id: string;
  task_name: string;
  date_string: string;
  task_status: TaskStatus;
  start_timestamp: number;
  finish_timestamp: number | null;
  data: Record<string, unknown>;
}

export interface TaskAgentMetadata {
  goal: string;
  stop_reason: string;
  total_steps: number;
  tool_calls_count: number;
  duration_seconds: number;
  token_usage: { prompt: number; completion: number; total: number };
  final_answer: string | null;
}

export interface TaskDetail extends TaskSummary {
  agent_metadata?: TaskAgentMetadata;
}

export interface ListTasksParams {
  status?: TaskStatus[];
  task_name?: string;
  date?: string;
  trace_id?: string;
  page?: number;
  page_size?: number;
}

export interface ListTasksData {
  total: number;
  page: number;
  page_size: number;
  items: TaskSummary[];
}

export interface RunTaskRequest {
  task_name: string;
  date_string?: string;
  [key: string]: unknown;
}

export interface RunTaskResponse {
  code: number;
  message: string;
  trace_id: string;
  data?: Record<string, unknown>;
}

export interface CancelTaskRequest {
  trace_id: string;
}

// ============ Trace Events ============

export type TraceEventType =
  // task_scheduler 层
  | 'task.accepted'
  | 'task.started'
  | 'task.finished'
  | 'task.cancel_requested'
  // harness 层
  | 'run_start'
  | 'step_start'
  | 'think_start'
  | 'think_end'
  | 'act_start'
  | 'act_end'
  | 'feedback_collected'
  | 'step_end'
  | 'improvement_recorded'
  | 'run_end'
  | 'run_error'
  | 'run_stopped'
  | string; // 兜底允许未来新增

export type TraceEventSource = 'task_scheduler' | 'harness' | string;

export interface TraceEvent {
  sequence: number;
  type: TraceEventType;
  trace_id: string;
  step: number | null;
  source: TraceEventSource;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface TraceEventsData {
  trace_id: string;
  closed: boolean;
  events: TraceEvent[];
}

// ============ Skills ============

export type RiskLevel = 'READ' | 'WRITE' | 'DESTRUCTIVE' | 'read' | 'write' | 'destructive';

export type SkillSource = 'system' | 'personal';
export type SkillType = 'executable' | 'knowledge';

export interface SkillParameter {
  type: string;
  description?: string;
  required?: boolean;
  default?: unknown;
}

export interface SkillInfo {
  skill_id: string;
  name: string;
  description: string;
  category: string;
  risk_level: RiskLevel;
  skill_type?: SkillType;
  parameters: Record<string, SkillParameter>;
  call_count_24h?: number;
  source: SkillSource;
  editable: boolean;
  markdown: string;
  tags?: string[];
  scope?: string;
}

export interface SkillCallRecord {
  trace_id: string;
  sequence: number;
  step: number | null;
  arguments: unknown;
  created_at: string;
}

export interface SkillCallsData {
  skill_name: string;
  calls: SkillCallRecord[];
}

// ============ Runs ============

export interface RunSummary {
  id: number;
  trace_id: string;
  goal: string;
  success: number;
  stop_reason: string;
  total_steps: number;
  tool_calls_count: number;
  final_answer: string | null;
  failed_tool_calls: Array<{ tool_name: string; error: string }> | null;
  token_usage: { prompt: number; completion: number; total: number } | null;
  prompt_version: string;
  created_at: string;
}

export interface ListRunsParams {
  success?: number;
  goal_keyword?: string;
  trace_id?: string;
  page?: number;
  page_size?: number;
}

export interface ListRunsData {
  total: number;
  page: number;
  page_size: number;
  items: RunSummary[];
}

// ============ Replay ============

export interface ReplayRequest {
  trace_id: string;
  model?: string;
}

export interface ReplayResult {
  trace_id: string;
  model: string;
  step: number;
  prompt_message_count: number;
  original: {
    final_answer: string | null;
    token_usage: { prompt: number; completion: number; total: number } | null;
  };
  replay: {
    final_answer: string | null;
    token_usage: { prompt: number; completion: number; total: number } | null;
  };
}

// ============ System ============

export type HealthFlag = 'ok' | 'degraded' | 'failed' | 'stopped';

export interface SystemStats {
  health: { mysql: HealthFlag; log_service: HealthFlag };
  counts: {
    running: number;
    success_24h: number;
    failed_24h: number;
    cancelled_24h: number;
  };
  throughput_24h: Array<{ hour: string; success: number; failed: number }>;
  recent_failures: Array<TaskSummary & { error?: string }>;
}

// ============ Chat ============

export type ChatMessageRole = 'user' | 'assistant' | 'tool' | 'system';

/** Agent 输出的 tool_call。后端落库时是 ToolCall.to_dict() 的形态。 */
export interface ChatToolCall {
  id?: string;
  name?: string;
  /** 部分序列化下会出现 OpenAI 风格嵌套 {function:{name,arguments}} */
  function?: { name?: string; arguments?: string };
  arguments?: Record<string, unknown> | string;
}

export type ChatMessageStatus = 0 | 1 | 2 | 3;
// 0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled

export interface ChatMessage {
  id: number;
  conversation_id: string;
  role: ChatMessageRole;
  content: string | null;
  tool_calls: ChatToolCall[] | null;
  tool_call_id: string | null;
  trace_id: string | null;
  token_usage: { prompt: number; completion: number; total: number } | null;
  status: ChatMessageStatus;
  created_at: string;
}

export enum ChatConversationStatus {
  ACTIVE = 0,
  ARCHIVED = 1,
  DELETED = 99,
}

export interface ChatConversation {
  conversation_id: string;
  title: string | null;
  status: ChatConversationStatus;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ListConversationsData {
  total: number;
  limit: number;
  offset: number;
  items: ChatConversation[];
}

export interface ConversationDetailData {
  conversation: ChatConversation;
  messages: ChatMessage[];
}

export interface SendChatMessageResponse {
  code: number;
  message: string;
  trace_id: string;
  data: { trace_id: string; conversation_id: string };
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string; // JSON string
  };
}

export interface ConfirmPlanRequest {
  message_id: number;
  action: 'confirm' | 'reject';
}

export interface ConfirmPlanResponse {
  code: number;
  message?: string;
  trace_id?: string;
}

// ============ Chat Agent Events (FE-1) ============

export type PlanStepStatus = 'pending' | 'in_progress' | 'done' | 'failed' | 'skipped';

export interface PlanStep {
  id?: string;
  goal: string;
  status: PlanStepStatus;
  error?: string;
}

/** chat.* SSE 事件常量（FE-1 / FE-5 / FE-6） */
export const CHAT_EVENTS = {
  TOKEN_DELTA: 'chat.token_delta',
  REASONING_DELTA: 'chat.reasoning_delta',
  TOOL_CALL_START: 'chat.tool_call_start',
  TOOL_CALL_END: 'chat.tool_call_end',
  TOOL_CALL_PROPOSED: 'chat.tool_call_proposed',
  TURN_PAUSED: 'chat.turn_paused',
  TURN_END: 'chat.turn_end',
  TURN_ERROR: 'chat.turn_error',
  MODE_CHANGED: 'chat.mode_changed',
  PLAN_UPDATED: 'chat.plan_updated',
  REFLECTION: 'chat.reflection',
  STRATEGY: 'chat.strategy',
  ARTIFACT_CREATED: 'chat.artifact_created',
  CONTEXT_COMPACTED: 'chat.context_compacted',
  CACHE_HIT: 'chat.cache_hit',
  LIFECYCLE_CHANGED: 'chat.lifecycle_changed',
} as const;

export type AgentLifecycleState = 'idle' | 'running' | 'paused' | 'stopped';

export interface TokenUsage {
  prompt: number;
  completion: number;
  total: number;
}

export interface ArtifactRef {
  id: string;
  summary?: string;
  mime_type?: string;
}

export interface ArtifactContent {
  id: string;
  content: string;
  offset: number;
  has_more: boolean;
  total_size?: number;
}

/** 消息结构化片段（FE-5 parts 模型） */
export type MessagePart =
  | { kind: 'text'; text: string }
  | { kind: 'reasoning'; text: string }
  | {
      kind: 'tool';
      toolName: string;
      arguments: Record<string, unknown> | string;
      status?: 'running' | 'completed' | 'failed';
      result?: unknown;
      callId?: string;
    }
  | { kind: 'plan'; steps: PlanStep[] }
  | { kind: 'artifact'; ref: ArtifactRef }
  | { kind: 'subagent'; traceId: string; goal: string; summary?: string };

export interface ApiRequestOptions {
  signal?: AbortSignal;
}
