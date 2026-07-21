-- ============================================================
-- TaskPilot 数据库初始化脚本
-- 执行方式：mysql -u root -p < init.sql
-- 注意：会先删除已有同名表，再重新创建
-- ============================================================

-- ============================================================
-- Drop all tables
-- ============================================================
DROP TABLE IF EXISTS schema_migrations;
DROP TABLE IF EXISTS trace_head;
DROP TABLE IF EXISTS agent_memory;
DROP TABLE IF EXISTS chat_messages;
DROP TABLE IF EXISTS chat_conversations;
DROP TABLE IF EXISTS agent_run_summaries;
DROP TABLE IF EXISTS agent_events;
DROP TABLE IF EXISTS task_manager;
DROP TABLE IF EXISTS account_daily_usage;
DROP TABLE IF EXISTS account_skills;
DROP TABLE IF EXISTS system_skills;
DROP TABLE IF EXISTS refresh_tokens;
DROP TABLE IF EXISTS access_tokens;
DROP TABLE IF EXISTS account_login_failures;
DROP TABLE IF EXISTS invite_codes;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS skill_store_dependencies;
DROP TABLE IF EXISTS skill_store_tags;
DROP TABLE IF EXISTS skill_store_keywords;
DROP TABLE IF EXISTS skill_store_files;
DROP TABLE IF EXISTS skill_store_registry;
DROP TABLE IF EXISTS skill_store_categories;
DROP TABLE IF EXISTS skill_dependencies;
DROP TABLE IF EXISTS skill_tags;
DROP TABLE IF EXISTS skill_keywords;
DROP TABLE IF EXISTS skill_files;
DROP TABLE IF EXISTS skill_registry;
DROP TABLE IF EXISTS skill_categories;

-- ============================================================
-- 任务引擎
-- ============================================================

CREATE TABLE task_manager (
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

-- ============================================================
-- Agent 可观测
-- ============================================================

CREATE TABLE agent_events (
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

CREATE TABLE agent_run_summaries (
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

-- ============================================================
-- Chat 对话
-- ============================================================

CREATE TABLE chat_conversations (
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

CREATE TABLE chat_messages (
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
    seq             INT            NULL
        COMMENT 'trace 内单增序号',
    parent_seq      INT            NULL
        COMMENT '父消息 seq，根为 NULL',
    branch_type     VARCHAR(32)    NULL
        COMMENT 'main/compression/reflection',
    token_usage     JSON           NULL,
    status          TINYINT        NOT NULL DEFAULT 0
        COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled',
    account_id      BIGINT         NOT NULL DEFAULT 0
        COMMENT '归属账户 ID，0=无主/系统',
    created_at      TIMESTAMP(3)   DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_conv_created (conversation_id, created_at),
    INDEX idx_trace_id (trace_id),
    INDEX idx_trace_seq (trace_id, seq),
    INDEX idx_account_id (account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 消息树 head 指针
-- ============================================================

CREATE TABLE trace_head (
    trace_id     VARCHAR(128) NOT NULL PRIMARY KEY,
    head_seq     INT          NOT NULL DEFAULT 0
        COMMENT '当前主路径最新 seq；0 = 尚无消息',
    next_seq     INT          NOT NULL DEFAULT 1
        COMMENT '下一条可分配 seq',
    account_id   BIGINT       NOT NULL DEFAULT 0,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Agent 跨 run 记忆（反思）
-- ============================================================

CREATE TABLE agent_memory (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL DEFAULT 0,
    scope_key       VARCHAR(256) NOT NULL
        COMMENT '检索键：通常是 task_name 或 goal 的归一化关键词',
    trace_id        VARCHAR(128) NULL
        COMMENT '产生该反思的 run',
    reflection      TEXT         NOT NULL
        COMMENT 'LLM 生成的经验反思正文',
    success         TINYINT      NOT NULL DEFAULT 0,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_account_scope (account_id, scope_key),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 账号系统
-- ============================================================

CREATE TABLE accounts (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    username            VARCHAR(64)  NOT NULL,
    email               VARCHAR(128) NOT NULL,
    password_hash       VARCHAR(256) NOT NULL
        COMMENT 'bcrypt hash (v1) 或 SHA-256 hex (v0 兼容)',
    password_salt       VARCHAR(64)  NULL DEFAULT NULL
        COMMENT '仅旧版 SHA-256 密码使用，bcrypt 内置盐',
    role                VARCHAR(16)  NOT NULL DEFAULT 'user'
        COMMENT '角色: admin / user',
    avatar_url          VARCHAR(128) NULL
        COMMENT '用户头像版本键，非空表示已上传',
    agent_avatar_url    VARCHAR(128) NULL
        COMMENT 'Agent 头像版本键，非空表示已上传',
    daily_token_limit   BIGINT       NOT NULL DEFAULT 100000
        COMMENT '每日 token 配额上限',
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX uk_username (username),
    UNIQUE INDEX uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE access_tokens (
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

CREATE TABLE refresh_tokens (
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

CREATE TABLE account_daily_usage (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id      BIGINT       NOT NULL,
    usage_date      DATE         NOT NULL,
    tokens_used     BIGINT       NOT NULL DEFAULT 0,
    UNIQUE INDEX uk_account_date (account_id, usage_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE account_skills (
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

CREATE TABLE account_login_failures (
    account_id      BIGINT       NOT NULL,
    ip_address      VARCHAR(45)  NOT NULL
        COMMENT '最近一次登录失败的 IP',
    fail_count      INT          NOT NULL DEFAULT 1
        COMMENT '连续失败次数',
    first_fail_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        COMMENT '首次失败时间',
    last_fail_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        COMMENT '最近失败时间',
    locked_until    TIMESTAMP    NULL
        COMMENT '锁定到期时间',
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

CREATE TABLE invite_codes (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    code            VARCHAR(32)  NOT NULL
        COMMENT '邀请码字符串',
    created_by      BIGINT       NOT NULL
        COMMENT '生成该邀请码的 admin account_id',
    used_by         BIGINT       NULL
        COMMENT '使用该邀请码注册的 account_id',
    status          TINYINT      NOT NULL DEFAULT 0
        COMMENT '0=未使用, 1=已使用',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    used_at         TIMESTAMP    NULL,
    UNIQUE INDEX uk_code (code),
    INDEX idx_status (status),
    INDEX idx_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE system_skills (
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
-- Skill Store — Claude Code Skill 文件目录的持久化存储与检索
-- ============================================================

CREATE TABLE skill_categories (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    slug            VARCHAR(64)  NOT NULL UNIQUE
        COMMENT '分类英文标识',
    name            VARCHAR(128) NOT NULL
        COMMENT '分类中文名',
    description     TEXT         NULL,
    sort_order      INT          DEFAULT 0,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO skill_categories (slug, name, sort_order) VALUES
    ('engineering',  '工程类',  1),
    ('arkcli',       'ARK CLI', 2),
    ('personal',     '个人',    3),
    ('productivity', '生产力',  4),
    ('in_progress',  '开发中',  5),
    ('misc',         '杂项',    6),
    ('deprecated',   '已弃用',  7);

CREATE TABLE skill_registry (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    dir_name        VARCHAR(128) NOT NULL UNIQUE
        COMMENT 'Skill 目录名，如 learn / arkcli-deploy',
    display_name    VARCHAR(256) NULL
        COMMENT 'frontmatter.name',
    description     TEXT         NULL
        COMMENT 'frontmatter.description — 供 Agent 选 skill 时扫描',
    version         VARCHAR(32)  NULL
        COMMENT 'frontmatter.version',
    frontmatter     JSON         NULL
        COMMENT '完整 frontmatter 原始数据（保留所有灵活字段）',
    category_id     INT          NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active'
        COMMENT 'active / in_progress / deprecated',
    source          VARCHAR(32)  NOT NULL DEFAULT 'third-party'
        COMMENT 'matt-pocock / arkcli / third-party / personal',
    file_count      INT          DEFAULT 0,
    total_size_bytes BIGINT      DEFAULT 0,
    content_plain   LONGTEXT     NULL
        COMMENT '所有文本文件拼接（供 FULLTEXT 搜索）',
    content_hash    VARCHAR(64)  NULL
        COMMENT 'content_plain 的 SHA-256，增量同步用',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_category (category_id),
    INDEX idx_status (status),
    INDEX idx_source (source),
    INDEX idx_dir_name (dir_name),
    FULLTEXT idx_ft_content (content_plain),
    FULLTEXT idx_ft_desc (description),
    FOREIGN KEY (category_id) REFERENCES skill_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE skill_files (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    skill_id        INT          NOT NULL,
    relative_path   VARCHAR(768) NOT NULL
        COMMENT 'skill 目录内的相对路径，如 REFERENCE.md / references/detail.md',
    filename        VARCHAR(255) NOT NULL,
    file_type       VARCHAR(16)  NOT NULL DEFAULT 'other'
        COMMENT 'skill_md / reference / example / manifest / script / readme / image / other',
    mime_type       VARCHAR(128) NULL,
    content         LONGTEXT     NULL
        COMMENT '文本文件内容；二进制留空',
    content_hash    VARCHAR(64)  NULL
        COMMENT '文件 SHA-256',
    file_size       INT          DEFAULT 0,
    is_primary      TINYINT      DEFAULT 0
        COMMENT '1 = SKILL.md',
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_skill_id (skill_id),
    INDEX idx_file_type (file_type),
    UNIQUE KEY uk_skill_file (skill_id, relative_path(255)),
    FULLTEXT idx_ft_file_content (content),
    FOREIGN KEY (skill_id) REFERENCES skill_registry(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE skill_keywords (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    skill_id    INT          NOT NULL,
    keyword     VARCHAR(128) NOT NULL
        COMMENT '触发词 / 搜索关键词',
    source      VARCHAR(32)  NOT NULL DEFAULT 'description_extracted'
        COMMENT 'frontmatter_keywords / description_extracted / manual',
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_skill_id (skill_id),
    INDEX idx_keyword (keyword),
    UNIQUE KEY uk_skill_kw (skill_id, keyword),
    FOREIGN KEY (skill_id) REFERENCES skill_registry(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE skill_tags (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    skill_id    INT          NOT NULL,
    tag         VARCHAR(64)  NOT NULL
        COMMENT '自由标签，跨分类标注',
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_skill_id (skill_id),
    INDEX idx_tag (tag),
    UNIQUE KEY uk_skill_tag (skill_id, tag),
    FOREIGN KEY (skill_id) REFERENCES skill_registry(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE skill_dependencies (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    source_skill_id     INT          NOT NULL
        COMMENT '引用方 skill_id',
    target_skill_id     INT          NOT NULL
        COMMENT '被引用方 skill_id',
    relation_type       VARCHAR(16)  NOT NULL DEFAULT 'references'
        COMMENT 'references / requires / extends / related',
    reference_path      VARCHAR(768) NULL
        COMMENT '引用来源的相对路径，如 ../arkcli-shared/SKILL.md',
    created_at          TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source_skill_id),
    INDEX idx_target (target_skill_id),
    UNIQUE KEY uk_dep (source_skill_id, target_skill_id, relation_type),
    FOREIGN KEY (source_skill_id) REFERENCES skill_registry(id) ON DELETE CASCADE,
    FOREIGN KEY (target_skill_id) REFERENCES skill_registry(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 迁移版本记录（init.sql 已包含所有迁移的列/表，标记为已应用）
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(64)  NOT NULL PRIMARY KEY
        COMMENT '已执行的迁移文件名（不含 .sql）',
    applied_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    checksum    VARCHAR(64)  NULL
        COMMENT '文件 SHA-256，用于检测文件被修改',
    INDEX idx_applied (applied_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO schema_migrations (version) VALUES ('001_message_tree'), ('002_account_avatars'), ('003_skill_store');

-- ============================================================
-- 默认管理员账号
-- 用户名: admin
-- 密码:   admin123
-- ⚠️ 生产环境请立即修改密码
-- ============================================================

INSERT INTO accounts (username, email, password_hash, password_salt, role, daily_token_limit)
VALUES ('admin', 'admin@taskpilot.local',
        '$2b$12$iL3bXV08uRAtCSFm49X42.BiVA/k2iKGMzNAgURxNY516/qMpnC6G',
        NULL, 'admin', 10000000);
