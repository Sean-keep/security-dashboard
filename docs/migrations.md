# 数据库迁移

本项目当前使用 `Base.metadata.create_all()` 做引导建表，**不引入 Alembic**。
这是有意的取舍，但有一个必须知道的限制：

> `create_all()` 只创建**缺失的表**，不会给已存在的表补列。
> 给已有模型加字段时，**必须**手工对线上库执行一次 `ALTER TABLE`。

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
| `mysql_init_dashboard.sql`（`docs/`） | 首次建库建表的基线 SQL | 历史 |

## 执行方式

### Docker Compose

```bash
docker exec -i sec-mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" security_dashboard \
  < backend/migrations/20260922_ingest_endpoint_token.sql
```

### 手工部署

```bash
mysql -u<user> -p<pass> security_dashboard \
  < backend/migrations/20260922_ingest_endpoint_token.sql
```

执行后脚本会 `SELECT` 出每个 ingest 端点新生成的 `token`。
把它填进发送端的 `X-Ingest-Token` 请求头即可；也可以之后在
**远程端点管理** 页面调用 `POST /api/remote/endpoints/{id}/rotate-token` 换新 token
（旧 token 立即失效）。

## 什么时候该引入 Alembic

满足下面任意一条就该迁到 Alembic，而不是继续堆 SQL 文件：

- 模型变更频繁（每周多次），手工 `ALTER` 开始漏做；
- 需要**回滚**（alembic `downgrade`），生产事故要求可逆；
- 多环境（dev / test / prod） schema 开始漂移，需要统一的版本号追踪。

在此之前，SQL 脚本 + `create_all()` 够用，也更容易在小团队里看清每一步做了什么。
