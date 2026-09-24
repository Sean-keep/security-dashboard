# 数据库迁移

本项目当前使用 `Base.metadata.create_all()` 做引导建表，**不引入 Alembic**。
这是有意的取舍，但有一个必须知道的限制：

> `create_all()` 只创建**缺失的表**，不会给已存在的表补列。
> 给已有模型加字段时，**必须**手工对线上库执行一次 `ALTER TABLE`。
>
> 旧库升上来后，用 [`scripts/check_mysql_schema.sql`](../scripts/check_mysql_schema.sql)
> 核对一遍（见 README「库表结构体检」）—— 缺列会被直接报出来并给出 `ALTER` 草稿。
> 模型加了字段也要在它的 `_sc_expect` 里补一行。

## 目录结构

```
backend/migrations/
  YYYYMMDD_description.sql   # 一次性、可重复执行的 DDL/DML 脚本
```

每个脚本必须满足：

1. **幂等** — 用 `information_schema` 守卫，重复执行不报错。
2. **可审计** — 文件头注释写清「为什么需要、对哪张表、什么时候引入」。
3. **默认可空或有回填** — 给已有行补列时提供 `UPDATE ... WHERE ... IS NULL`。

## 已有迁移

| 文件 | 作用 | 引入时间 |
| --- | --- | --- |
| `20260922_ingest_endpoint_token.sql` | `ingest_endpoints` 新增 `token` 列 + 索引，并给旧端点回填 token | 2026-09-22 |
| `20260923_alert_fingerprint_dedup.sql` | `alerts` 新增 `fingerprint` / `last_seen_at`，告警按指纹去重 | 2026-09-23 |
| `20260923_ingest_idempotency_and_liveness.sql` | `ingest_logs` 新增 `sent_at` / `message_id` + 唯一索引；`ingest_endpoints.last_received_at` 存活时间 | 2026-09-23 |
| `20260923_ingest_senders.sql` | 远程发送端识别（首次特征 + 配对绑定） | 2026-09-23 |
| `20260923_rbac_separation.sql` | 三权分立角色集；把 `users.role='admin'` 升级为 `sys_admin` | 2026-09-23 |
| `20260924_role_permissions.sql` | `role_permissions` 表：角色 → 权限点矩阵，含默认五行 | 2026-09-24 |
| `20260924_scheduler_observability.sql` | `rule_execution_logs` 新增 `duration_ms` / `triggered_by`；把 `scheduler_*` 挪到 `runtime` 分组（不进系统设置页） | 2026-09-24 |
| `mysql_init_dashboard.sql`（`docs/`） | 首次建库建表的基线 SQL | 历史 |

## 执行方式

### 单体容器（推荐）

```bash
./scripts/deploy.sh migrate      # 跑 backend/migrations/ 下所有 .sql，全部幂等
```

### Docker Compose

```bash
docker compose exec -T mysql mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" security_dashboard \
  < backend/migrations/<文件名>.sql
```

### 手工部署

```bash
mysql -u<user> -p<pass> security_dashboard < backend/migrations/<文件名>.sql
```

> **注意**：`20260922_ingest_endpoint_token.sql` 末尾会 `SELECT` 出每个 ingest
> 端点的 `token`，方便拷进发送端的 `X-Ingest-Token` 请求头。这在部署日志里会
> 留下明文 —— 跑完记得确认日志去向。也可以之后在**远程端点管理**页面调用
> `POST /api/remote/endpoints/{id}/rotate-token` 换新 token（旧 token 立即失效）。

## 什么时候该引入 Alembic

满足下面任意一条就该迁到 Alembic，而不是继续堆 SQL 文件：

- 模型变更频繁（每周多次），手工 `ALTER` 开始漏做；
- 需要**回滚**（alembic `downgrade`），生产事故要求可逆；
- 多环境（dev / test / prod） schema 开始漂移，需要统一的版本号追踪。

在此之前，SQL 脚本 + `create_all()` 够用，也更容易在小团队里看清每一步做了什么。
