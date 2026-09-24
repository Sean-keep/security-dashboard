-- 调度器可观测性：执行日志加耗时和触发来源；运行态键挪出配置面。
--
-- 背景：调度器一直「绿着灯但一条规则都没跑」是发现不了的 ——
--   1. `misfire_grace_time` 一过 / `max_instances=1` 丢弃，什么都不留痕；
--   2. 执行日志没有耗时，「这条规则从 2 秒涨到 2 分钟」看不出来；
--   3. trigger 埋在 detail 的 JSON 里，SQL 查不了；
--   4. 心跳写在 system_config，又被 GET /settings/config 原样吐到界面上。
--
-- 幂等：每列都用 information_schema 守着，重复执行安全。
-- 列名刻意不用 `trigger` —— 那是 MySQL 保留字。

SET @has_dur := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'rule_execution_logs'
    AND COLUMN_NAME  = 'duration_ms'
);
SET @ddl := IF(
  @has_dur = 0,
  'ALTER TABLE rule_execution_logs ADD COLUMN duration_ms INT NOT NULL DEFAULT 0',
  'SELECT "rule_execution_logs.duration_ms already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_trg := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'rule_execution_logs'
    AND COLUMN_NAME  = 'triggered_by'
);
SET @ddl := IF(
  @has_trg = 0,
  'ALTER TABLE rule_execution_logs ADD COLUMN triggered_by VARCHAR(32) NOT NULL DEFAULT ''scheduler'', ADD INDEX ix_rule_execution_logs_triggered_by (triggered_by)',
  'SELECT "rule_execution_logs.triggered_by already present, skipping" AS note'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 旧行补默认值：把 detail JSON 里的 trigger 提到列上，顺手把历史归成 scheduler。
UPDATE rule_execution_logs SET triggered_by = 'scheduler' WHERE triggered_by = '' OR triggered_by IS NULL;

-- 心跳这类**运行态**键挪到 runtime 分组。GET /settings/config 会按 group_name
-- 过滤掉 runtime，系统设置页从此看不到 scheduler_heartbeat 那行时间戳。
UPDATE system_config SET group_name = 'runtime' WHERE `key` LIKE 'scheduler_%';
