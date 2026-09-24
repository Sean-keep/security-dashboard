-- ============================================================================
-- 库表结构体检 —— 旧版本升上来之后缺表 / 缺列 / 类型不适配
-- ============================================================================
--
-- 为什么需要：建表走 SQLAlchemy 的 Base.metadata.create_all()，它**只补缺失的
-- 表，绝不给已有表补列**。从旧版本升上来最常见的事故就是「表在、列没了」：
--
--     rule_execution_logs 新加了 duration_ms
--     → create_all 看见表已存在，跳过
--     → INSERT 带上 duration_ms
--     → OperationalError: no column named duration_ms
--
-- 本脚本把线上库的真实结构（information_schema）跟下面 _sc_expect 里的**期望
-- 结构**对一遍，报出缺表 / 缺列 / 类型不符，并打印补齐用的 SQL。**不改业务数据。**
--
-- 用法：
--     mysql -u<user> -p<pass> security_dashboard < scripts/check_mysql_schema.sql
--
-- 单体容器里：
--     docker exec -i security-dashboard-v2 sh -c \
--       'set -a; . /opt/security-dashboard/backend/.env; set +a; \
--        mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
--       < scripts/check_mysql_schema.sql
--
-- 输出五个结果集：
--   ① 缺表      整张表没有。启动时 create_all() 会建，但建的是**当前**结构
--   ② 缺列      create_all() 补不了，必须 ALTER —— 最常见的升级事故
--   ③ 类型不符  老字段类型跟现在对不上，跑起来会静默出错
--   ④ 补齐脚本  按「先建表 → 再加列 → 最后改类型」排好序，可直接拷去执行
--   ⑤ 结论      三个数字，全是 0 就说明结构对得上
--
-- 维护：模型加了字段，在下面 _sc_expect 里加一行即可（共 6 列）：
--   (表名, 列名, MySQL类型, 类型族, 是否NOT NULL, 是否主键)
-- 类型族只用来比对，取值 int/bool/float/str/text/datetime/date/time/json/blob。
--
-- 实现备注：中间结果用的是**普通表**（_sc_* 前缀，跑完即删），不是 TEMPORARY
-- 表 —— MySQL 不允许 TEMPORARY 表在同一条语句里被引用两次，UNION 各支共用
-- 期望表时会直接报 `Can't reopen table`。
-- ============================================================================

SET SESSION group_concat_max_len = 1024000;
SET NAMES utf8mb4;

-- 期望结构（当前模型快照，2026-09-24，18 表 / 183 列）
DROP TABLE IF EXISTS _sc_expect;
CREATE TABLE _sc_expect (
  tbl      VARCHAR(64) NOT NULL,
  col      VARCHAR(64) NOT NULL,
  col_type VARCHAR(64) NOT NULL,   -- 生成 ALTER 用的 MySQL 写法
  fam      VARCHAR(16) NOT NULL,   -- 类型族，比对用
  notnull  TINYINT     NOT NULL,
  is_pk    TINYINT     NOT NULL
) DEFAULT CHARSET utf8mb4;

INSERT INTO _sc_expect (tbl, col, col_type, fam, notnull, is_pk) VALUES
  ('addresses','id','INT','int',1,1),
  ('addresses','ip_address','VARCHAR(64)','str',1,0),
  ('addresses','country','VARCHAR(128)','str',0,0),
  ('addresses','domain','VARCHAR(256)','str',0,0),
  ('addresses','start_time','DATETIME','datetime',0,0),
  ('addresses','end_time','DATETIME','datetime',0,0),
  ('addresses','duration','INT','int',0,0),
  ('addresses','attack_count','INT','int',0,0),
  ('addresses','severity','VARCHAR(32)','str',0,0),
  ('addresses','status','VARCHAR(32)','str',0,0),
  ('addresses','source','VARCHAR(64)','str',0,0),
  ('addresses','remark','TEXT','text',0,0),
  ('addresses','created_at','DATETIME','datetime',1,0),
  ('addresses','updated_at','DATETIME','datetime',1,0),
  ('alerts','id','INT','int',1,1),
  ('alerts','rule_id','INT','int',0,0),
  ('alerts','rule_name','VARCHAR(128)','str',0,0),
  ('alerts','title','VARCHAR(256)','str',1,0),
  ('alerts','content','TEXT','text',0,0),
  ('alerts','src_ip','VARCHAR(64)','str',0,0),
  ('alerts','dst_ip','VARCHAR(64)','str',0,0),
  ('alerts','event_count','INT','int',0,0),
  ('alerts','severity','VARCHAR(32)','str',0,0),
  ('alerts','status','VARCHAR(32)','str',0,0),
  ('alerts','category','VARCHAR(64)','str',0,0),
  ('alerts','handle_suggestion','TEXT','text',0,0),
  ('alerts','raw_log','TEXT','text',0,0),
  ('alerts','raw_logs','MEDIUMTEXT','text',0,0),
  ('alerts','fingerprint','VARCHAR(64)','str',0,0),
  ('alerts','last_seen_at','DATETIME','datetime',0,0),
  ('alerts','created_at','DATETIME','datetime',0,0),
  ('alerts','confirmed_at','DATETIME','datetime',0,0),
  ('alerts','resolved_at','DATETIME','datetime',0,0),
  ('custom_metrics','id','INT','int',1,1),
  ('custom_metrics','name','VARCHAR(128)','str',1,0),
  ('custom_metrics','description','TEXT','text',0,0),
  ('custom_metrics','promql','TEXT','text',1,0),
  ('custom_metrics','unit','VARCHAR(32)','str',0,0),
  ('custom_metrics','created_at','DATETIME','datetime',1,0),
  ('custom_metrics','updated_at','DATETIME','datetime',1,0),
  ('ingest_endpoints','id','INT','int',1,1),
  ('ingest_endpoints','name','VARCHAR(64)','str',1,0),
  ('ingest_endpoints','description','TEXT','text',0,0),
  ('ingest_endpoints','token','VARCHAR(64)','str',0,0),
  ('ingest_endpoints','last_received_at','DATETIME','datetime',0,0),
  ('ingest_endpoints','created_at','DATETIME','datetime',0,0),
  ('ingest_endpoints','updated_at','DATETIME','datetime',0,0),
  ('ingest_logs','id','INT','int',1,1),
  ('ingest_logs','endpoint_id','INT','int',1,0),
  ('ingest_logs','endpoint_name','VARCHAR(64)','str',1,0),
  ('ingest_logs','sender_id','INT','int',0,0),
  ('ingest_logs','payload','TEXT','text',0,0),
  ('ingest_logs','sent_at','DATETIME','datetime',0,0),
  ('ingest_logs','message_id','VARCHAR(128)','str',0,0),
  ('ingest_logs','received_at','DATETIME','datetime',0,0),
  ('ingest_senders','id','INT','int',1,1),
  ('ingest_senders','endpoint_id','INT','int',1,0),
  ('ingest_senders','endpoint_name','VARCHAR(64)','str',1,0),
  ('ingest_senders','fingerprint','VARCHAR(64)','str',1,0),
  ('ingest_senders','src_ip','VARCHAR(64)','str',0,0),
  ('ingest_senders','user_agent','VARCHAR(256)','str',0,0),
  ('ingest_senders','content_type','VARCHAR(128)','str',0,0),
  ('ingest_senders','payload_shape','VARCHAR(256)','str',0,0),
  ('ingest_senders','display_name','VARCHAR(128)','str',0,0),
  ('ingest_senders','status','VARCHAR(16)','str',0,0),
  ('ingest_senders','sample_payload','TEXT','text',0,0),
  ('ingest_senders','send_count','INT','int',0,0),
  ('ingest_senders','first_seen_at','DATETIME','datetime',0,0),
  ('ingest_senders','last_seen_at','DATETIME','datetime',0,0),
  ('ingest_senders','bound_at','DATETIME','datetime',0,0),
  ('inspection_reports','id','INT','int',1,1),
  ('inspection_reports','report_date','VARCHAR(20)','str',1,0),
  ('inspection_reports','generated_at','VARCHAR(30)','str',1,0),
  ('inspection_reports','address_count','INT','int',0,0),
  ('inspection_reports','script_count','INT','int',0,0),
  ('inspection_reports','content','MEDIUMTEXT','text',1,0),
  ('inspection_reports','scripts_json','MEDIUMTEXT','text',0,0),
  ('inspection_reports','created_by','VARCHAR(100)','str',0,0),
  ('inspection_reports','created_at','DATETIME','datetime',0,0),
  ('login_logs','id','INT','int',1,1),
  ('login_logs','username','VARCHAR(64)','str',0,0),
  ('login_logs','ip_address','VARCHAR(64)','str',0,0),
  ('login_logs','user_agent','VARCHAR(512)','str',0,0),
  ('login_logs','status','VARCHAR(32)','str',0,0),
  ('login_logs','reason','VARCHAR(128)','str',0,0),
  ('login_logs','created_at','DATETIME','datetime',0,0),
  ('operation_logs','id','INT','int',1,1),
  ('operation_logs','log_type','VARCHAR(50)','str',0,0),
  ('operation_logs','username','VARCHAR(100)','str',0,0),
  ('operation_logs','action','VARCHAR(255)','str',0,0),
  ('operation_logs','target','VARCHAR(255)','str',0,0),
  ('operation_logs','ip_address','VARCHAR(50)','str',0,0),
  ('operation_logs','status','VARCHAR(50)','str',0,0),
  ('operation_logs','detail','TEXT','text',0,0),
  ('operation_logs','created_at','DATETIME','datetime',0,0),
  ('remote_executions','id','INT','int',1,1),
  ('remote_executions','host_id','INT','int',1,0),
  ('remote_executions','host_alias','VARCHAR(128)','str',0,0),
  ('remote_executions','script_id','INT','int',0,0),
  ('remote_executions','script_name','VARCHAR(128)','str',0,0),
  ('remote_executions','stdout','TEXT','text',0,0),
  ('remote_executions','stderr','TEXT','text',0,0),
  ('remote_executions','exit_code','INT','int',0,0),
  ('remote_executions','received_at','DATETIME','datetime',0,0),
  ('remote_executions','created_at','DATETIME','datetime',0,0),
  ('remote_hosts','id','INT','int',1,1),
  ('remote_hosts','alias','VARCHAR(128)','str',1,0),
  ('remote_hosts','token','VARCHAR(64)','str',1,0),
  ('remote_hosts','last_seen','DATETIME','datetime',0,0),
  ('remote_hosts','created_at','DATETIME','datetime',0,0),
  ('remote_hosts','created_by','VARCHAR(64)','str',0,0),
  ('role_permissions','id','INT','int',1,1),
  ('role_permissions','role','VARCHAR(32)','str',1,0),
  ('role_permissions','permissions','TEXT','text',0,0),
  ('role_permissions','updated_at','DATETIME','datetime',0,0),
  ('role_permissions','updated_by','VARCHAR(64)','str',0,0),
  ('rule_execution_logs','id','INT','int',1,1),
  ('rule_execution_logs','rule_id','INT','int',1,0),
  ('rule_execution_logs','rule_name','VARCHAR(255)','str',0,0),
  ('rule_execution_logs','executed_at','DATETIME','datetime',0,0),
  ('rule_execution_logs','alert_count','INT','int',0,0),
  ('rule_execution_logs','detail','TEXT','text',0,0),
  ('rule_execution_logs','status','VARCHAR(50)','str',0,0),
  ('rule_execution_logs','error_message','TEXT','text',0,0),
  ('rule_execution_logs','duration_ms','INT','int',0,0),
  ('rule_execution_logs','triggered_by','VARCHAR(32)','str',0,0),
  ('rules','id','INT','int',1,1),
  ('rules','name','VARCHAR(128)','str',1,0),
  ('rules','description','TEXT','text',0,0),
  ('rules','nodes','TEXT','text',0,0),
  ('rules','stages','TEXT','text',0,0),
  ('rules','output_mapping','TEXT','text',0,0),
  ('rules','es_index','VARCHAR(256)','str',0,0),
  ('rules','schedule_type','VARCHAR(32)','str',0,0),
  ('rules','schedule_value','VARCHAR(128)','str',0,0),
  ('rules','is_enabled','TINYINT(1)','bool',0,0),
  ('rules','actions','TEXT','text',0,0),
  ('rules','last_run','DATETIME','datetime',0,0),
  ('rules','next_run','DATETIME','datetime',0,0),
  ('rules','run_count','INT','int',0,0),
  ('rules','created_by','INT','int',0,0),
  ('rules','created_at','DATETIME','datetime',1,0),
  ('rules','updated_at','DATETIME','datetime',1,0),
  ('script_run_logs','id','INT','int',1,1),
  ('script_run_logs','script_id','INT','int',0,0),
  ('script_run_logs','script_name','VARCHAR(128)','str',0,0),
  ('script_run_logs','script_version_hash','VARCHAR(32)','str',0,0),
  ('script_run_logs','script_type','VARCHAR(32)','str',0,0),
  ('script_run_logs','run_by','VARCHAR(64)','str',0,0),
  ('script_run_logs','trigger','VARCHAR(32)','str',0,0),
  ('script_run_logs','exit_code','INT','int',0,0),
  ('script_run_logs','duration_ms','INT','int',0,0),
  ('script_run_logs','stdout_tail','MEDIUMTEXT','text',0,0),
  ('script_run_logs','stderr_tail','MEDIUMTEXT','text',0,0),
  ('script_run_logs','error','TEXT','text',0,0),
  ('script_run_logs','started_at','DATETIME','datetime',0,0),
  ('script_run_logs','finished_at','DATETIME','datetime',0,0),
  ('scripts','id','INT','int',1,1),
  ('scripts','name','VARCHAR(128)','str',1,0),
  ('scripts','script_type','VARCHAR(32)','str',0,0),
  ('scripts','description','TEXT','text',0,0),
  ('scripts','content','TEXT','text',1,0),
  ('scripts','is_active','TINYINT(1)','bool',0,0),
  ('scripts','created_at','DATETIME','datetime',0,0),
  ('scripts','updated_at','DATETIME','datetime',0,0),
  ('system_config','id','INT','int',1,1),
  ('system_config','key','VARCHAR(128)','str',1,0),
  ('system_config','value','TEXT','text',0,0),
  ('system_config','label','VARCHAR(128)','str',0,0),
  ('system_config','description','VARCHAR(256)','str',0,0),
  ('system_config','group_name','VARCHAR(64)','str',0,0),
  ('system_config','updated_at','DATETIME','datetime',0,0),
  ('users','id','INT','int',1,1),
  ('users','username','VARCHAR(64)','str',1,0),
  ('users','password_hash','VARCHAR(256)','str',1,0),
  ('users','nickname','VARCHAR(128)','str',0,0),
  ('users','role','VARCHAR(32)','str',0,0),
  ('users','is_active','TINYINT(1)','bool',0,0),
  ('users','last_login','DATETIME','datetime',0,0),
  ('users','login_count','INT','int',0,0),
  ('users','error_count','INT','int',0,0),
  ('users','locked_until','DATETIME','datetime',0,0),
  ('users','created_at','DATETIME','datetime',0,0);

-- 线上库的真实结构，类型收成族。
-- 刻意不比类型字符串：BOOL 在 MySQL 里是 tinyint(1)，MEDIUMTEXT/TEXT 都算
-- text，拿字符串比对出来的全是噪音。
DROP TABLE IF EXISTS _sc_live;
CREATE TABLE _sc_live AS
SELECT
  c.TABLE_NAME  AS tbl,
  c.COLUMN_NAME AS col,
  c.COLUMN_TYPE AS col_type,
  CASE
    WHEN c.COLUMN_TYPE = 'tinyint(1)' OR c.DATA_TYPE IN ('bool','boolean') THEN 'bool'
    WHEN c.DATA_TYPE IN ('tinyint','smallint','mediumint','int','integer','bigint') THEN 'int'
    WHEN c.DATA_TYPE IN ('float','double','real','decimal','numeric')         THEN 'float'
    WHEN c.DATA_TYPE IN ('datetime','timestamp')                             THEN 'datetime'
    WHEN c.DATA_TYPE = 'date'                                                THEN 'date'
    WHEN c.DATA_TYPE = 'time'                                                THEN 'time'
    WHEN c.DATA_TYPE IN ('tinytext','text','mediumtext','longtext')          THEN 'text'
    WHEN c.DATA_TYPE IN ('char','varchar','enum','set','nchar','nvarchar')   THEN 'str'
    WHEN c.DATA_TYPE = 'json'                                                THEN 'json'
    WHEN c.DATA_TYPE IN ('tinyblob','blob','mediumblob','longblob',
                         'binary','varbinary')                               THEN 'blob'
    ELSE c.DATA_TYPE
  END AS fam
FROM information_schema.COLUMNS c
WHERE c.TABLE_SCHEMA = DATABASE();

-- 哪些预期表在库里压根没有
DROP TABLE IF EXISTS _sc_missing_tbl;
CREATE TABLE _sc_missing_tbl AS
SELECT DISTINCT e.tbl
FROM _sc_expect e
WHERE NOT EXISTS (
  SELECT 1 FROM information_schema.TABLES t
  WHERE t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = e.tbl
);

-- 缺列。defval 是补列时的默认值 —— 给已有行补列时 NOT NULL 且没 DEFAULT
-- 会直接失败，所以统一带上一个按类型给的安全默认值。
DROP TABLE IF EXISTS _sc_missing_col;
CREATE TABLE _sc_missing_col AS
SELECT e.tbl, e.col, e.col_type, e.fam, e.notnull,
       CASE e.fam
         WHEN 'int'      THEN '0'
         WHEN 'bool'     THEN '0'
         WHEN 'float'    THEN '0'
         WHEN 'datetime' THEN '''2026-01-01 00:00:00'''
         ELSE ''''''
       END AS defval
FROM _sc_expect e
WHERE e.is_pk = 0                                      -- 主键列不该用 ADD COLUMN 补
  AND e.tbl NOT IN (SELECT tbl FROM _sc_missing_tbl)   -- 整表缺失归 ①
  AND NOT EXISTS (SELECT 1 FROM _sc_live l WHERE l.tbl = e.tbl AND l.col = e.col);

-- 类型不符。text <-> str 之间不报：不同版本反射出来很乱，互相之间当兼容
DROP TABLE IF EXISTS _sc_type_mismatch;
CREATE TABLE _sc_type_mismatch AS
SELECT e.tbl, e.col, e.col_type AS want_type, e.notnull,
       l.col_type AS have_type, e.fam AS want_fam, l.fam AS have_fam
FROM _sc_expect e
JOIN _sc_live l ON l.tbl = e.tbl AND l.col = e.col
WHERE e.fam <> l.fam
  AND NOT (e.fam IN ('text','str') AND l.fam IN ('text','str'))
  AND e.tbl NOT IN (SELECT tbl FROM _sc_missing_tbl);

-- ============================================================================
-- ① 缺表
-- ============================================================================
SELECT '① 缺表' AS `检查项`,
       m.tbl   AS `表名`,
       NULL    AS `列名`,
       CONCAT('整张表没有（模型里有 ',
              (SELECT COUNT(*) FROM _sc_expect e WHERE e.tbl = m.tbl),
              ' 个列）。启动时 create_all() 会按当前结构建出来。') AS `说明`
FROM _sc_missing_tbl m
ORDER BY m.tbl;

-- ============================================================================
-- ② 缺列  —— create_all() 补不了，必须 ALTER
-- ============================================================================
SELECT '② 缺列' AS `检查项`,
       m.tbl AS `表名`,
       m.col AS `列名`,
       CONCAT('ALTER TABLE `', m.tbl, '` ADD COLUMN `', m.col, '` ', m.col_type,
              IF(m.notnull = 1, ' NOT NULL', ' NULL'),
              ' DEFAULT ', m.defval, ';') AS `修复SQL`
FROM _sc_missing_col m
ORDER BY m.tbl, m.col;

-- ============================================================================
-- ③ 类型不符  —— 只报告。MODIFY 会动已有数据，得人看过再改
-- ============================================================================
SELECT '③ 类型不符' AS `检查项`,
       t.tbl AS `表名`,
       t.col AS `列名`,
       CONCAT('模型 ', t.want_type, '（', t.want_fam, '）  vs  库 ',
              t.have_type, '（', t.have_fam, '）',
              '   →  ALTER TABLE `', t.tbl, '` MODIFY COLUMN `', t.col, '` ',
              t.want_type, IF(t.notnull = 1, ' NOT NULL', ' NULL'),
              ';   -- 会动已有数据，先确认再执行') AS `说明`
FROM _sc_type_mismatch t
ORDER BY t.tbl, t.col;

-- ============================================================================
-- ④ 补齐脚本  —— 先建表 → 再加列 → 最后改类型，可直接拷去执行
-- ============================================================================
SELECT '④ 补齐脚本' AS `检查项`, x.stmt AS `可执行SQL`
FROM (
  SELECT 1 AS seq, tbl AS k,
         CONCAT('CREATE TABLE IF NOT EXISTS `', tbl, '` (\n  ',
                GROUP_CONCAT(
                  CONCAT('`', col, '` ', col_type,
                         IF(notnull = 1, ' NOT NULL', ''),
                         IF(is_pk = 1, ' PRIMARY KEY', ''))
                  ORDER BY is_pk DESC, col SEPARATOR ',\n  '
                ),
                '\n);') AS stmt
  FROM _sc_expect
  WHERE tbl IN (SELECT tbl FROM _sc_missing_tbl)
  GROUP BY tbl

  UNION ALL
  SELECT 2, tbl,
         CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN `', col, '` ', col_type,
                IF(notnull = 1, ' NOT NULL', ' NULL'),
                ' DEFAULT ', defval, ';')
  FROM _sc_missing_col

  UNION ALL
  SELECT 3, tbl,
         CONCAT('-- 需人工确认（会动已有数据）\n',
                'ALTER TABLE `', tbl, '` MODIFY COLUMN `', col, '` ',
                want_type, IF(notnull = 1, ' NOT NULL', ' NULL'), ';')
  FROM _sc_type_mismatch
) x
ORDER BY x.seq, x.k;

-- ============================================================================
-- ⑤ 结论  —— 三个数字全是 0 就说明结构对得上
-- ============================================================================
SELECT '⑤ 结论' AS `检查项`,
       (SELECT COUNT(*) FROM _sc_missing_tbl)   AS `缺表`,
       (SELECT COUNT(*) FROM _sc_missing_col)   AS `缺列`,
       (SELECT COUNT(*) FROM _sc_type_mismatch) AS `类型不符`;

-- 收拾干净，不留痕迹
DROP TABLE IF EXISTS _sc_expect, _sc_live, _sc_missing_tbl, _sc_missing_col, _sc_type_mismatch;
