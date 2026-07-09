-- 账号头像：用户 / Agent 图片路径键（用于缓存 bust）
ALTER TABLE accounts
    ADD COLUMN avatar_url VARCHAR(128) NULL
        COMMENT '用户头像版本键，非空表示已上传'
        AFTER role,
    ADD COLUMN agent_avatar_url VARCHAR(128) NULL
        COMMENT 'Agent 头像版本键，非空表示已上传'
        AFTER avatar_url;
