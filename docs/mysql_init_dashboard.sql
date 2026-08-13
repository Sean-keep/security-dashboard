-- ============================================================
-- 安全态势监控平台 - MySQL 8 完整初始化 SQL
-- 库名: dashboard  (如实际使用 dashboarh，请全文替换)
-- 字符集: utf8mb4 / utf8mb4_unicode_ci
-- 引擎: InnoDB
-- 说明: 表结构与 backend/app/models/*.py 完全一致。
--       外键要求被引用表先建，已按依赖顺序排列。
-- ============================================================

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS dashboard
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dashboard;

-- ------------------------------------------------------------
-- 1. users (用户)  —— 被 rules.created_by 引用，必须先建
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id           INT          NOT NULL AUTO_INCREMENT,
  username     VARCHAR(64)  NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  nickname     VARCHAR(128) DEFAULT '',
  role         VARCHAR(32)  DEFAULT 'operator',
  is_active    TINYINT(1)   DEFAULT 1,
  last_login   DATETIME     NULL,
  login_count  INT          DEFAULT 0,
  error_count  INT          DEFAULT 0,
  locked_until DATETIME     NULL,
  created_at   DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 2. login_logs (登录日志)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS login_logs (
  id          INT       NOT NULL AUTO_INCREMENT,
  username    VARCHAR(64) DEFAULT '',
  ip_address  VARCHAR(64) DEFAULT '',
  user_agent  VARCHAR(512) DEFAULT '',
  status      VARCHAR(32) DEFAULT 'fail',
  reason      VARCHAR(128) DEFAULT '',
  created_at  DATETIME  NULL,
  PRIMARY KEY (id),
  KEY ix_login_logs_username (username),
  KEY ix_login_logs_ip_address (ip_address),
  KEY ix_login_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 3. rules (规则)  —— 引用 users.id
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rules (
  id              INT       NOT NULL AUTO_INCREMENT,
  name            VARCHAR(128) NOT NULL,
  description     TEXT,
  nodes           TEXT,
  stages          TEXT,
  output_mapping  TEXT,
  es_index        VARCHAR(256) DEFAULT 'security-logs-*',
  schedule_type   VARCHAR(32)  DEFAULT 'once',
  schedule_value  VARCHAR(128) DEFAULT '',
  is_enabled      TINYINT(1)   DEFAULT 1,
  actions         TEXT,
  last_run        DATETIME     NULL,
  next_run        DATETIME     NULL,
  run_count       INT          DEFAULT 0,
  created_by      INT          NULL,
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL,
  PRIMARY KEY (id),
  KEY ix_rules_created_by (created_by),
  CONSTRAINT fk_rules_created_by FOREIGN KEY (created_by)
    REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 4. system_config (系统配置 KV)  —— key 是保留字，必须反引号
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_config (
  id          INT       NOT NULL AUTO_INCREMENT,
  `key`       VARCHAR(128) NOT NULL,
  value       TEXT,
  label       VARCHAR(128) DEFAULT '',
  description  VARCHAR(256) DEFAULT '',
  group_name  VARCHAR(64)  DEFAULT 'general',
  updated_at  DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_system_config_key (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 5. addresses (攻击地址)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS addresses (
  id           INT       NOT NULL AUTO_INCREMENT,
  ip_address   VARCHAR(64) NOT NULL,
  country      VARCHAR(128) DEFAULT '',
  domain       VARCHAR(256) DEFAULT '',
  start_time   DATETIME     NULL,
  end_time     DATETIME     NULL,
  duration     INT          DEFAULT 0,
  attack_count INT          DEFAULT 0,
  severity     VARCHAR(32)  DEFAULT 'medium',
  status       VARCHAR(32)  DEFAULT 'active',
  source       VARCHAR(64)  DEFAULT '',
  remark       TEXT,
  created_at   DATETIME     NOT NULL,
  updated_at   DATETIME     NOT NULL,
  PRIMARY KEY (id),
  KEY ix_addresses_ip_address (ip_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 6. alerts (告警)  —— 引用 rules.id
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
  id             INT       NOT NULL AUTO_INCREMENT,
  rule_id        INT          NULL,
  rule_name      VARCHAR(128) DEFAULT '',
  title          VARCHAR(256) NOT NULL,
  content        TEXT,
  src_ip         VARCHAR(64)  DEFAULT '',
  dst_ip         VARCHAR(64)  DEFAULT '',
  event_count    INT          DEFAULT 1,
  severity       VARCHAR(32)  DEFAULT 'medium',
  status         VARCHAR(32)  DEFAULT 'pending',
  category       VARCHAR(64)  DEFAULT '',
  handle_suggestion TEXT,
  raw_log        TEXT,
  created_at     DATETIME     NULL,
  confirmed_at   DATETIME     NULL,
  resolved_at    DATETIME     NULL,
  PRIMARY KEY (id),
  KEY ix_alerts_rule_id (rule_id),
  KEY ix_alerts_src_ip (src_ip),
  KEY ix_alerts_created_at (created_at),
  CONSTRAINT fk_alerts_rule_id FOREIGN KEY (rule_id)
    REFERENCES rules (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 7. scripts (脚本)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scripts (
  id          INT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(128) NOT NULL,
  script_type VARCHAR(32)  DEFAULT 'python',
  description TEXT,
  content     TEXT         NOT NULL,
  is_active   TINYINT(1)   DEFAULT 1,
  created_at  DATETIME     NULL,
  updated_at  DATETIME     NULL,
  PRIMARY KEY (id),
  KEY ix_scripts_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 8. custom_metrics (自定义指标)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS custom_metrics (
  id          INT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(128) NOT NULL,
  description TEXT,
  promql      TEXT         NOT NULL,
  unit        VARCHAR(32)  DEFAULT '',
  created_at  DATETIME     NOT NULL,
  updated_at  DATETIME     NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_custom_metrics_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 9. rule_execution_logs (规则执行日志)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_execution_logs (
  id            INT       NOT NULL AUTO_INCREMENT,
  rule_id       INT       NOT NULL,
  rule_name     VARCHAR(255) DEFAULT '',
  executed_at   DATETIME  NULL,
  alert_count   INT       DEFAULT 0,
  detail        TEXT,
  status        VARCHAR(50) DEFAULT 'success',
  error_message TEXT      NULL,
  PRIMARY KEY (id),
  KEY ix_rule_execution_logs_rule_id (rule_id),
  KEY ix_rule_execution_logs_executed_at (executed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 10. ingest_endpoints (自定义 API 接收接口)  —— 被 ingest_logs 引用
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_endpoints (
  id          INT       NOT NULL AUTO_INCREMENT,
  name        VARCHAR(64) NOT NULL,
  description TEXT      NULL,
  created_at  DATETIME  NULL,
  updated_at  DATETIME  NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_ingest_endpoints_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 11. ingest_logs (接收数据日志)  —— 引用 ingest_endpoints.id (CASCADE)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_logs (
  id            INT       NOT NULL AUTO_INCREMENT,
  endpoint_id   INT       NOT NULL,
  endpoint_name VARCHAR(64) NOT NULL,
  payload       TEXT      NULL,
  received_at   DATETIME  NULL,
  PRIMARY KEY (id),
  KEY ix_ingest_logs_endpoint_id (endpoint_id),
  KEY ix_ingest_logs_endpoint_name (endpoint_name),
  KEY ix_ingest_logs_received_at (received_at),
  KEY ix_ingest_logs_endpoint_received (endpoint_id, received_at),
  CONSTRAINT fk_ingest_logs_endpoint_id FOREIGN KEY (endpoint_id)
    REFERENCES ingest_endpoints (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 12. inspection_reports (巡检报告)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inspection_reports (
  id            INT       NOT NULL AUTO_INCREMENT,
  report_date   VARCHAR(20) NOT NULL,
  generated_at  VARCHAR(30) NOT NULL,
  address_count INT       DEFAULT 0,
  script_count  INT       DEFAULT 0,
  content       TEXT      NOT NULL,
  scripts_json  TEXT      NULL,
  created_by    VARCHAR(100) DEFAULT 'admin',
  created_at    DATETIME  NULL,
  PRIMARY KEY (id),
  KEY ix_inspection_reports_report_date (report_date),
  KEY ix_inspection_reports_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 13. operation_logs (统一操作/登录日志)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operation_logs (
  id          INT       NOT NULL AUTO_INCREMENT,
  log_type    VARCHAR(50) DEFAULT 'operation',
  username    VARCHAR(100) DEFAULT '',
  action      VARCHAR(255) DEFAULT '',
  target      VARCHAR(255) NULL,
  ip_address  VARCHAR(50)  NULL,
  status      VARCHAR(50)  DEFAULT 'success',
  detail      TEXT      NULL,
  created_at  DATETIME  NULL,
  PRIMARY KEY (id),
  KEY ix_operation_logs_log_type (log_type),
  KEY ix_operation_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 14. remote_executions (远程执行结果)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS remote_executions (
  id          INT       NOT NULL AUTO_INCREMENT,
  host_id     INT       NOT NULL,
  host_alias  VARCHAR(128) DEFAULT '',
  script_id   INT       NULL,
  script_name VARCHAR(128) DEFAULT '',
  stdout      TEXT,
  stderr      TEXT,
  exit_code   INT       DEFAULT 0,
  received_at DATETIME  NULL,
  created_at  DATETIME  NULL,
  PRIMARY KEY (id),
  KEY ix_remote_executions_host_id (host_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 15. remote_hosts (远程孤岛主机)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS remote_hosts (
  id          INT       NOT NULL AUTO_INCREMENT,
  alias       VARCHAR(128) NOT NULL,
  token       VARCHAR(64)  NOT NULL,
  last_seen   DATETIME     NULL,
  created_at  DATETIME     NULL,
  created_by  VARCHAR(64)  DEFAULT '',
  PRIMARY KEY (id),
  UNIQUE KEY uk_remote_hosts_alias (alias),
  UNIQUE KEY uk_remote_hosts_token (token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 初始系统配置项（ES / MySQL / Grafana / Prometheus）
-- 缺失这些 key 时，前端设置页无法显示对应配置项，
-- 且 save_config 会跳过保存、连接测试读默认值（localhost/空）导致失败
-- ============================================================
INSERT INTO system_config (`key`, value, label, description, group_name, updated_at) VALUES
  ('prometheus_url', 'http://localhost:9090', 'Prometheus 地址', 'Prometheus 服务地址', 'prometheus', NOW()),
  ('prometheus_user', '', 'Prometheus 用户', 'Basic Auth 用户名（可选）', 'prometheus', NOW()),
  ('prometheus_password', '', 'Prometheus 密码', 'Basic Auth 密码（可选）', 'prometheus', NOW()),
  ('es_host', '', 'ES 地址', 'Elasticsearch 主机地址', 'es', NOW()),
  ('es_port', '9200', 'ES 端口', 'Elasticsearch 端口', 'es', NOW()),
  ('es_scheme', 'https', 'ES 协议', 'http 或 https', 'es', NOW()),
  ('es_verify_certs', 'false', 'ES 验证证书', 'https 时是否验证证书 (true/false)', 'es', NOW()),
  ('es_user', '', 'ES 用户名', 'Elasticsearch 用户名（可选）', 'es', NOW()),
  ('es_password', '', 'ES 密码', 'Elasticsearch 密码（可选）', 'es', NOW()),
  ('es_index', 'security-logs-*', 'ES 索引', '查询使用的索引通配符', 'es', NOW()),
  ('mysql_host', 'localhost', 'MySQL 地址', 'MySQL 主机地址', 'mysql', NOW()),
  ('mysql_port', '3306', 'MySQL 端口', 'MySQL 端口', 'mysql', NOW()),
  ('mysql_user', 'root', 'MySQL 用户', 'MySQL 用户名', 'mysql', NOW()),
  ('mysql_password', '', 'MySQL 密码', 'MySQL 密码', 'mysql', NOW()),
  ('mysql_database', 'security_dashboard', 'MySQL 数据库', '数据库名', 'mysql', NOW()),
  ('grafana_url', '', 'Grafana 地址', 'Grafana URL，如 http://192.168.1.100:3000', 'grafana', NOW()),
  ('grafana_auth_mode', 'apikey', 'Grafana 认证方式', 'apikey 或 basic', 'grafana', NOW()),
  ('grafana_api_key', '', 'Grafana API Key', 'API Key（可选）', 'grafana', NOW()),
  ('grafana_user', '', 'Grafana 用户名', 'Basic Auth 用户名（可选）', 'grafana', NOW()),
  ('grafana_password', '', 'Grafana 密码', 'Basic Auth 密码（可选）', 'grafana', NOW())
ON DUPLICATE KEY UPDATE value=VALUES(value), label=VALUES(label), description=VALUES(description), group_name=VALUES(group_name), updated_at=NOW();

-- ============================================================
-- 默认管理员账号 (密码: 123456)
-- 哈希由 bcrypt==4.0.1 / passlib==1.7.4 生成，与后端一致
-- ============================================================
INSERT INTO users (username, password_hash, nickname, role, is_active, login_count, error_count, created_at)
VALUES (
  'admin',
  '$2b$12$uvw0u4gdDA8SfWfAjV8ApuVyfQ6CoD4nAxVT0bhi//l31/SmCWgTW',
  '管理员',
  'admin',
  1,
  0,
  0,
  NOW()
);
