-- Migration: metric-threshold rule type (rules.source_type / metric_config)
--            + the per-series sustain state table rule_metric_states
--
-- Why: new rule type "metric" — PromQL + comparison operator + threshold +
-- 持续 N 分钟, e.g. 「CPU 持续 5 分钟 80% → 发 TG」. It lives in the platform's
-- own rule list alongside the ES log rules (source_type routes execution).
--
-- `rule_metric_states` must be a real table: "continuously breaching since" is
-- cross-run state, and the APScheduler JobStore is in-memory across two
-- processes (uvicorn + run_scheduler). One row per (rule, series_key); GC'd
-- when a series vanishes or the rule is deleted / disabled / reconfigured.
--
-- Idempotent: guarded by information_schema, safe to run more than once.

SET @has_src := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'rules'
    AND COLUMN_NAME  = 'source_type'
);
SET @ddl := IF(
  @has_src = 0,
  'ALTER TABLE rules ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT ''logs''',
  'SELECT "rules.source_type already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_cfg := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'rules'
    AND COLUMN_NAME  = 'metric_config'
);
SET @ddl := IF(
  @has_cfg = 0,
  'ALTER TABLE rules ADD COLUMN metric_config TEXT NULL',
  'SELECT "rules.metric_config already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 老规则全部是查 ES 的。回填而不是靠 DEFAULT —— 旧行的列值在 ALTER 之后是
-- DEFAULT 没错，但显式写一遍可以让「升级后 source_type 全是 NULL」这种半吊子
-- 状态也修好。
UPDATE rules SET source_type = 'logs'  WHERE source_type IS NULL OR source_type = '';
UPDATE rules SET metric_config = '{}'  WHERE metric_config IS NULL;

CREATE TABLE IF NOT EXISTS rule_metric_states (
    id              INT NOT NULL AUTO_INCREMENT,
    rule_id         INT NOT NULL,
    series_key      VARCHAR(64) NOT NULL,
    series_labels   TEXT NOT NULL,
    breach_since    DATETIME NULL,
    firing          TINYINT(1) NOT NULL DEFAULT 0,
    -- 反引号必须有：LAST_VALUE 在 MySQL 8.0 是保留字（窗口函数），
    -- 裸写会让整个 CREATE TABLE 语法错误。SQLAlchemy 生成的 DDL 自己会加
    -- 反引号，所以只有这段手写迁移需要写。
    `last_value`    DOUBLE NULL,
    last_check_at   DATETIME NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_metric_state_rule_series (rule_id, series_key),
    KEY ix_rule_metric_states_rule_id (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
