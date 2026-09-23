-- 发送方识别 + 人工绑定（接收端认人）
-- 远程端脚本不动，token 变可选；第一包特征聚成发送方，绑定后才进日报。
-- 幂等，可重复跑。

CREATE TABLE IF NOT EXISTS ingest_senders (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    endpoint_id     INT NOT NULL,
    endpoint_name   VARCHAR(64) NOT NULL,
    fingerprint     VARCHAR(64) NOT NULL,
    src_ip          VARCHAR(64) DEFAULT '',
    user_agent      VARCHAR(256) DEFAULT '',
    content_type    VARCHAR(128) DEFAULT '',
    payload_shape   VARCHAR(256) DEFAULT '',
    display_name    VARCHAR(128) DEFAULT '',
    status          VARCHAR(16) DEFAULT 'pending',
    sample_payload  LONGTEXT NULL,
    send_count      INT DEFAULT 0,
    first_seen_at   DATETIME NULL,
    last_seen_at    DATETIME NULL,
    bound_at        DATETIME NULL,
    UNIQUE KEY uq_ingest_senders_endpoint_fp (endpoint_id, fingerprint),
    KEY ix_ingest_senders_endpoint_id (endpoint_id),
    KEY ix_ingest_senders_endpoint_name (endpoint_name),
    KEY ix_ingest_senders_fingerprint (fingerprint),
    KEY ix_ingest_senders_status (status),
    KEY ix_ingest_senders_last_seen_at (last_seen_at),
    KEY ix_ingest_senders_endpoint_status (endpoint_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ingest_logs 归属发送方。历史行 sender_id 为 NULL（那时还分不出发送方）。
SET @col := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'ingest_logs'
      AND COLUMN_NAME = 'sender_id'
);
SET @ddl := IF(@col = 0,
    'ALTER TABLE ingest_logs ADD COLUMN sender_id INT NULL, ADD INDEX ix_ingest_logs_sender_id (sender_id)',
    'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
