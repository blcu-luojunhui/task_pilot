CREATE TABLE IF NOT EXISTS task_manager (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    date_string      VARCHAR(64)    NULL,
    task_name        VARCHAR(256)   NULL,
    task_status      TINYINT        NOT NULL DEFAULT 0
        COMMENT '0:INIT 1:PROCESSING 2:SUCCESS 3:CANCELLED 4:CANCEL_REQUESTED 99:FAILED',
    start_timestamp  BIGINT         NULL,
    finish_timestamp BIGINT         NULL,
    trace_id         VARCHAR(128)   NULL,
    data             JSON           NULL,
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_date_task (date_string, task_name),
    INDEX idx_status_task_name (task_status, task_name),
    INDEX idx_task_name (task_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_events (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(128)   NOT NULL,
    sequence        INT            NOT NULL,
    event_type      VARCHAR(64)    NOT NULL,
    source          VARCHAR(32)    NOT NULL,
    step            INT            NULL,
    payload         JSON           NULL,
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_trace_seq (trace_id, sequence),
    INDEX idx_trace_step (trace_id, step),
    INDEX idx_type_time (event_type, created_at),
    INDEX idx_trace_id (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_run_summaries (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(128)   NOT NULL,
    goal            TEXT           NULL,
    success         TINYINT        NOT NULL DEFAULT 0,
    stop_reason     VARCHAR(64)    NULL,
    total_steps     INT            NOT NULL DEFAULT 0,
    tool_calls_count INT           NOT NULL DEFAULT 0,
    final_answer    TEXT           NULL,
    failed_tool_calls JSON         NULL,
    token_usage     JSON           NULL,
    prompt_version  VARCHAR(64)    NULL,
    metadata        JSON           NULL,
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_success (success),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_conversations (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(64)    NOT NULL
        COMMENT '对外稳定 ID，格式 Conv-YYYYmmddHHMMSS-xxxxxxxx',
    title           VARCHAR(255)   NULL,
    status          TINYINT        NOT NULL DEFAULT 0
        COMMENT '0:ACTIVE 1:ARCHIVED 99:DELETED',
    metadata        JSON           NULL
        COMMENT '预留扩展：user_id / tags / agent_config 覆盖',
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_conversation_id (conversation_id),
    INDEX idx_status_updated (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS chat_messages (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(64)    NOT NULL,
    role            VARCHAR(16)    NOT NULL
        COMMENT 'user / assistant / tool / system',
    content         LONGTEXT       NULL
        COMMENT 'assistant 仅 tool_calls 时可为 NULL',
    tool_calls      JSON           NULL
        COMMENT 'assistant 的工具调用列表 [{id,name,arguments}]',
    tool_call_id    VARCHAR(128)   NULL
        COMMENT 'role=tool 时关联的 call id',
    trace_id        VARCHAR(128)   NULL
        COMMENT '本轮 chat task 的 trace_id，可关联 agent_events / agent_run_summaries',
    token_usage     JSON           NULL,
    status          TINYINT        NOT NULL DEFAULT 0
        COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled',
    created_at      TIMESTAMP(3)   DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_conv_created (conversation_id, created_at),
    INDEX idx_trace_id (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 兼容已有数据库：chat_messages 新增 status 列（MySQL 5.7 不支持 IF NOT EXISTS，需手动判断执行）
-- ALTER TABLE chat_messages ADD COLUMN status TINYINT NOT NULL DEFAULT 0 COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled' AFTER token_usage;
