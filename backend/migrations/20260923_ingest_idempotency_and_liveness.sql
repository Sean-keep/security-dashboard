-- Migration: ingest idempotency + source-time ordering + endpoint liveness
--
-- Why: `Base.metadata.create_all()` only creates missing *tables*. A live MySQL
-- database created before 2026-09-23 will not gain these columns on boot, and
-- `reports.py` now orders "latest ingest" by `sent_at` — without the column that
-- query fails at runtime.
--
-- Columns added:
--   ingest_logs.sent_at       — 源端声明的发送时间 (X-Sent-At)。重试送达的旧批次
--                               会排在新批次后面，取「最新一条」必须用它而不是 id。
--   ingest_logs.message_id    — 幂等键 (X-Message-Id)。推送端遇到 429/5xx 会重试，
--                               没有它就是重复行。
--   ingest_endpoints.last_received_at — 存活信号，分不清「agent 挂了」和「本来就没数据」。
--
-- Idempotent: guarded by information_schema, safe to run more than once.
-- Run as a user with ALTER privilege on the dashboard schema.

SET @has_sent_at := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'ingest_logs'
    AND COLUMN_NAME  = 'sent_at'
);
SET @ddl := IF(
  @has_sent_at = 0,
  'ALTER TABLE ingest_logs ADD COLUMN sent_at DATETIME NULL, ADD INDEX ix_ingest_logs_sent_at (sent_at)',
  'SELECT "ingest_logs.sent_at already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_message_id := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'ingest_logs'
    AND COLUMN_NAME  = 'message_id'
);
SET @ddl := IF(
  @has_message_id = 0,
  'ALTER TABLE ingest_logs ADD COLUMN message_id VARCHAR(128) NULL',
  'SELECT "ingest_logs.message_id already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 唯一索引 (endpoint_id, message_id)：MySQL 允许多个 NULL，所以没带
-- X-Message-Id 的旧源端不受影响。
SET @has_uq := (
  SELECT COUNT(*) FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'ingest_logs'
    AND INDEX_NAME   = 'uq_ingest_logs_endpoint_msg'
);
SET @ddl := IF(
  @has_uq = 0,
  'ALTER TABLE ingest_logs ADD UNIQUE KEY uq_ingest_logs_endpoint_msg (endpoint_id, message_id)',
  'SELECT "uq_ingest_logs_endpoint_msg already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_last_recv := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'ingest_endpoints'
    AND COLUMN_NAME  = 'last_received_at'
);
SET @ddl := IF(
  @has_last_recv = 0,
  'ALTER TABLE ingest_endpoints ADD COLUMN last_received_at DATETIME NULL',
  'SELECT "ingest_endpoints.last_received_at already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 回填 last_received_at，否则所有既有端口一上线就显示「已静默」。
UPDATE ingest_endpoints ep
  JOIN (
        SELECT endpoint_id, MAX(received_at) AS latest
          FROM ingest_logs
         GROUP BY endpoint_id
       ) m ON m.endpoint_id = ep.id
   SET ep.last_received_at = m.latest
 WHERE ep.last_received_at IS NULL;

-- 回填 sent_at = received_at：旧行没有源端时间，用接收时间是唯一合理近似，
-- 也让 ORDER BY sent_at DESC, id DESC 对旧行退化成原来的 id 排序。
UPDATE ingest_logs SET sent_at = received_at WHERE sent_at IS NULL;
