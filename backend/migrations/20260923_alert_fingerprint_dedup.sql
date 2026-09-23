-- Migration: alert de-duplication fingerprint + last_seen_at
--
-- Why: every rule hit inserted a fresh alert row. A noisy rule firing every
-- minute produced hundreds of identical "pending" alerts and a Telegram
-- message per hit. `fingerprint` = sha1(rule_id|src_ip|title) lets the executor
-- fold repeats into one row (event_count++, last_seen_at=now) inside a cooldown
-- window, and push TG only on the transition.
--
-- Idempotent: guarded by information_schema, safe to run more than once.

SET @has_fp := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'alerts'
    AND COLUMN_NAME  = 'fingerprint'
);
SET @ddl := IF(
  @has_fp = 0,
  'ALTER TABLE alerts ADD COLUMN fingerprint VARCHAR(64) NOT NULL DEFAULT '''', ADD INDEX ix_alerts_fingerprint (fingerprint)',
  'SELECT "alerts.fingerprint already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_seen := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'alerts'
    AND COLUMN_NAME  = 'last_seen_at'
);
SET @ddl := IF(
  @has_seen = 0,
  'ALTER TABLE alerts ADD COLUMN last_seen_at DATETIME NULL, ADD INDEX ix_alerts_last_seen_at (last_seen_at)',
  'SELECT "alerts.last_seen_at already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 旧行没有源端去重信息，用创建时间是唯一合理近似，也让冷却判断对旧行退化成
-- 「按创建时间看」而不是「永远不冷却」。
UPDATE alerts SET last_seen_at = created_at WHERE last_seen_at IS NULL;

-- 旧行补 fingerprint，否则同一条规则的第一次新告警和它自己的重复无法配对。
-- 只补 src_ip/title 非空的行，和 rule_executor._alert_fingerprint 的算法一致。
UPDATE alerts
   SET fingerprint = SHA1(CONCAT(COALESCE(rule_id, 0), '|', COALESCE(src_ip, ''), '|', COALESCE(title, '')))
 WHERE fingerprint = '' OR fingerprint IS NULL;
