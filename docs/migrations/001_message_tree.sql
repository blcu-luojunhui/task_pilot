-- 001_message_tree
-- 新增 chat_messages 树结构列 + trace_head 表
-- 非破坏式：只 ADD COLUMN / CREATE TABLE，不丢数据

ALTER TABLE chat_messages
  ADD COLUMN seq INT NULL COMMENT 'trace 内单增序号' AFTER trace_id,
  ADD COLUMN parent_seq INT NULL COMMENT '父消息 seq，根 NULL' AFTER seq,
  ADD COLUMN branch_type VARCHAR(32) NULL COMMENT 'main/compression/reflection' AFTER parent_seq;

CREATE INDEX idx_trace_seq ON chat_messages (trace_id, seq);

CREATE TABLE IF NOT EXISTS trace_head (
    trace_id     VARCHAR(128) NOT NULL PRIMARY KEY,
    head_seq     INT          NOT NULL DEFAULT 0
        COMMENT '当前主路径最新 seq；0 = 尚无消息',
    next_seq     INT          NOT NULL DEFAULT 1
        COMMENT '下一条可分配 seq',
    account_id   BIGINT       NOT NULL DEFAULT 0,
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
