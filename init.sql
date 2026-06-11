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
    account_id       BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_date_task (date_string, task_name),
    INDEX idx_status_task_name (task_status, task_name),
    INDEX idx_task_name (task_name),
    INDEX idx_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS agent_events (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id        VARCHAR(128)   NOT NULL,
    sequence        INT            NOT NULL,
    event_type      VARCHAR(64)    NOT NULL,
    source          VARCHAR(32)    NOT NULL,
    step            INT            NULL,
    payload         JSON           NULL,
    account_id      BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_trace_seq (trace_id, sequence),
    INDEX idx_trace_step (trace_id, step),
    INDEX idx_type_time (event_type, created_at),
    INDEX idx_trace_id (trace_id),
    INDEX idx_account_id (account_id)
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
    account_id      BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_success (success),
    INDEX idx_created (created_at),
    INDEX idx_account_id (account_id)
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
    account_id      BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_conversation_id (conversation_id),
    INDEX idx_status_updated (status, updated_at),
    INDEX idx_account_id (account_id)
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
    account_id      BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    created_at      TIMESTAMP(3)   DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_conv_created (conversation_id, created_at),
    INDEX idx_trace_id (trace_id),
    INDEX idx_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 兼容已有数据库：chat_messages 新增 status 列（MySQL 5.7 不支持 IF NOT EXISTS，需手动判断执行）
-- ALTER TABLE chat_messages ADD COLUMN status TINYINT NOT NULL DEFAULT 0 COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled' AFTER token_usage;

-- ============================================================
-- 账号系统
-- ============================================================

CREATE TABLE IF NOT EXISTS accounts (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    username            VARCHAR(64)  NOT NULL,
    email               VARCHAR(128) NOT NULL,
    password_hash       VARCHAR(256) NOT NULL
        COMMENT 'bcrypt hash (v1) 或 SHA-256 hex (v0 兼容)',
    password_salt       VARCHAR(64)  NULL DEFAULT NULL
        COMMENT '仅旧版 SHA-256 密码使用，bcrypt 内置盐',
    role                VARCHAR(16)  NOT NULL DEFAULT 'user'
        COMMENT '角色: admin / user',
    daily_token_limit   BIGINT       NOT NULL DEFAULT 100000
        COMMENT '每日 token 配额上限',
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_username (username),
    UNIQUE INDEX uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS access_tokens (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL,
    token_hash      VARCHAR(128) NOT NULL
        COMMENT 'SHA-256(token)',
    token_prefix    VARCHAR(12)  NOT NULL
        COMMENT 'Token 前缀 (sk-xxxxxxxx)，用于 UI 展示',
    name            VARCHAR(128) NULL
        COMMENT 'Token 备注名',
    last_used_at    TIMESTAMP    NULL,
    expires_at      TIMESTAMP    NULL,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_token_hash (token_hash),
    INDEX idx_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL,
    token_hash      VARCHAR(128) NOT NULL
        COMMENT 'SHA-256(refresh_token)',
    token_prefix    VARCHAR(12)  NOT NULL,
    access_token_id BIGINT       NULL
        COMMENT '关联的 access_token id',
    last_used_at    TIMESTAMP    NULL,
    expires_at      TIMESTAMP    NULL,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_rtoken_hash (token_hash),
    INDEX idx_rt_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS account_daily_usage (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL,
    usage_date      DATE         NOT NULL,
    tokens_used     BIGINT       NOT NULL DEFAULT 0,
    UNIQUE INDEX uk_account_date (account_id, usage_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS account_skills (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL,
    name            VARCHAR(128) NOT NULL
        COMMENT 'Skill 唯一标识（slug）',
    category        VARCHAR(64)  NOT NULL DEFAULT 'general'
        COMMENT '分类目录',
    description     VARCHAR(512) NOT NULL DEFAULT ''
        COMMENT '简短描述',
    scope           VARCHAR(64)  NOT NULL DEFAULT 'agent:*',
    content         MEDIUMTEXT   NOT NULL
        COMMENT '完整 Markdown 文件内容',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_account_skill_name (account_id, name),
    INDEX idx_account_category (account_id, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS system_skills (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(128) NOT NULL
        COMMENT 'Skill 唯一标识（slug）',
    category        VARCHAR(64)  NOT NULL DEFAULT 'general',
    description     VARCHAR(512) NOT NULL DEFAULT '',
    scope           VARCHAR(64)  NOT NULL DEFAULT 'agent:*',
    content         MEDIUMTEXT   NOT NULL
        COMMENT '完整 Markdown 文件内容',
    skill_type      VARCHAR(16)  NOT NULL DEFAULT 'knowledge'
        COMMENT 'executable / knowledge',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_system_skill_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 数据隔离迁移：为已有数据库添加 account_id 列
-- MySQL 5.7 不兼容 IF NOT EXISTS for ALTER TABLE ADD COLUMN，
-- 若列已存在会报错，忽略即可。
-- ============================================================

-- ALTER TABLE task_manager ADD COLUMN account_id BIGINT NOT NULL DEFAULT 0 COMMENT '归属账户 ID，0=无主/系统', ADD INDEX idx_account_id (account_id);
-- ALTER TABLE agent_events ADD COLUMN account_id BIGINT NOT NULL DEFAULT 0 COMMENT '归属账户 ID，0=无主/系统', ADD INDEX idx_account_id (account_id);
-- ALTER TABLE agent_run_summaries ADD COLUMN account_id BIGINT NOT NULL DEFAULT 0 COMMENT '归属账户 ID，0=无主/系统', ADD INDEX idx_account_id (account_id);
-- ALTER TABLE chat_conversations ADD COLUMN account_id BIGINT NOT NULL DEFAULT 0 COMMENT '归属账户 ID，0=无主/系统', ADD INDEX idx_account_id (account_id);
-- ALTER TABLE chat_messages ADD COLUMN account_id BIGINT NOT NULL DEFAULT 0 COMMENT '归属账户 ID，0=无主/系统', ADD INDEX idx_account_id (account_id);
