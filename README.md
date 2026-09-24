# Security Dashboard V2

安全监控平台 —— FastAPI + Vue 3 + MySQL + Elasticsearch。

主要作用是**写巡检报告**：把 ES 里的攻击日志、脚本执行结果、远程端上报的数据聚成可交付的 Word / TXT 报告。

支持两种部署方式：**Docker（推荐）** 和 **手动部署**。

## 目录

- [技术栈](#技术栈)
- [功能模块](#功能模块)
- [三权分立](#三权分立)
- [调度器架构](#调度器架构)
- [快速启动（Docker）](#快速启动docker推荐)
- [手动部署](#手动部署不使用-docker)
- [数据库迁移](#数据库迁移)
- [库表结构体检](#库表结构体检)
- [测试](#测试)
- [监控接入](#监控接入metrics)
- [初始账号](#初始账号)
- [告警规则说明](#告警规则说明)

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + Element Plus + ECharts + Pinia |
| 后端 | FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| 调度 | APScheduler 3.11（独立进程） |
| 存储 | MySQL 8（业务数据）+ Elasticsearch 8（原始日志） |
| 部署 | Docker / Docker Compose + Nginx |

### 前置：日志范式化

ES 里的日志需要先范式化。当前用 logstash，nginx 日志的 grok 配置：

```grok
match => [
  "message", '(?<src_ip>[0-9a-fA-F:.]+) - - \[(?<log_time>\S+) \+0530\] "(?<request_method>\S+)\s(?<request_url>\S+)\s\S+\s(?<request_status>\d+)\s(?<request_leng>\d+).*',
  "message", '(?<log_time>\S+\s\S+)\s\[(?<log_level>\S+)\]\s(?<pid>\S+)\:\s\S+\s(?<error_msg>.*)\sclient\:\s(?<src_ip>[0-9a-fA-F:.]+),\sserver\:\s(?<server_name>\S+),\srequest\:\s(?<request>.*),\shost:.*'
]
```

## 功能模块

### 业务

| 模块 | 说明 |
|------|------|
| **仪表盘** | 告警概览、趋势、Top 攻击 IP |
| **原始日志** | Kibana 风格的 ES 查询界面：索引/字段/时间范围/查询语句/结果表格 |
| **地址列表** | 攻击 IP 台账，自动查询归属地，可一键封禁 |
| **告警管理** | 模板渲染、去重（指纹 + 冷却窗口）、危险等级自动升降、**CSV 导出**、批量处理 |
| **规则管理** | 多阶段聚合规则、跨索引关联、AND/OR/NOT 条件树、告警趋势火花线、**Telegram 推送**（可先发测试消息） |
| **调度中心** | 调度器健康条、任务清单、近 24h 执行时间线、漏跑/失败统计、立即执行 |
| **脚本执行** | 自定义巡检脚本，带超时与内存闸门 |
| **巡检报告** | 按日期生成 Word / TXT 报告，含 Top 攻击、服务器指标、脚本结果 |
| **远程接收** | 开放端口接收远程端上报的数据（供日报取数），支持多端点、幂等去重、配对绑定 |
| **系统监控** | Grafana + Prometheus 指标展示（需配置数据源） |

### 系统设置

| 面板 | 说明 |
|------|------|
| **用户管理** | 建号 / 禁用 / 重置密码；**不含改角色**（改角色归授权） |
| **权限管理** | 角色 → 权限点矩阵，可勾选分配；三条底线硬校验（见下） |
| **界面管理** | 主题、主色、表格密度、侧边栏默认折叠、站点标题（全站一套） |
| **连接设置** | ES / MySQL / Grafana 连接配置与连通性测试 |
| **安全设置** | 登录锁定策略、VirusTotal 密钥、数据保留天数、Metrics 令牌 |
| **日志中心** | 登录日志 + 操作日志，支持筛选 |

### 主动作配置

规则触发后可配置：

- **写入 MySQL** — 落到地址列表
- **创建告警** — 模板渲染 `{src_ip}` / `{stage1.count}` 等占位符；条件满足时自动升危
- **推送到 Telegram** — 按规则独立配置 bot_token / chat_id；单次最多 20 条防刷屏

## 三权分立

权限模型按等保「三权分立」划分。三个**特权点**互斥：

| 权限点 | 含义 | 在任角色（默认） |
|--------|------|------------------|
| `manage_accounts` | 账号管理（建号/禁用/重置密码） | 系统管理员 `sys_admin` |
| `manage_authz` | 授权管理（改角色、改权限矩阵） | 安全管理员 `sec_admin` |
| `audit` | 审计（日志中心） | 审计管理员 `audit_admin` |

非特权点 `manage_system`（系统配置）和 `operate`（业务操作）可自由分配。

| 角色 | 账号 | 授权 | 审计 | 系统配置 | 业务操作 |
|------|:----:|:----:|:----:|:--------:|:--------:|
| `sys_admin` 系统管理员 | ✅ | — | — | ✅ | ✅ |
| `sec_admin` 安全管理员 | — | ✅ | — | — | ✅ |
| `audit_admin` 审计管理员 | — | — | ✅ | — | — |
| `operator` 业务操作员 | — | — | — | — | ✅ |
| `viewer` 只读用户 | — | — | — | — | — |

矩阵本身可在**权限管理**页勾选调整（`manage_accounts` 或 `manage_authz` 持有者均可），但三条底线由 `validate_role_matrix` 硬校验，勾也踩不过去：

1. **三权互斥** — 一个角色不能同时握两项三权
2. **三权独占** — 每项三权只认一个在任角色
3. **三权必须有人接** — 每项三权至少有一个角色持有（否则平台锁死）

另有两条账号护栏：不能删除/禁用/改自己的角色；不能把最后一个在任系统管理员撤掉。

> 旧库里的 `admin` 角色在启动时会被自动升级为 `sys_admin`（`_migrate_legacy_roles`）。

## 调度器架构

**两个进程**：uvicorn（Web）+ `run_scheduler.py`（调度器）。APScheduler 用内存 JobStore，两个进程够不着对方的 job，所以**不引 IPC，改成对账**：

```
rules.py 改规则  →  置 scheduler_dirty = 1（system_config）
run_scheduler.py →  每 5 秒看一眼脏位，有就 reconcile
                 →  每 60 秒兜底全量对账一次 + 写进程心跳
```

几个必须知道的约定：

- **对账时不能无脑重加 job** —— `IntervalTrigger` 一被 replace 就把起算点重置，每分钟 reconcile 一次的话定时规则永远不会触发。`_job_specs` 记着调度参数指纹，没变就不碰。
- **双心跳** —— `scheduler_heartbeat` 是「主循环还在转」，`scheduler_last_activity` 是「最近一次真正跑完的任务」。只看前者会漏掉线程池卡死（绿灯骗人）。
- **漏跑留痕** —— `misfire_grace_time` 一过 / `max_instances=1` 丢弃，都会写一条 `status='missed'` 的执行日志。以前这两件事什么都不留。
- **执行只有一条路径** —— `app/services/rule_runner.py:run_rule()`，手动执行和定时执行都调它，只有 `triggered_by` 标记不同。
- **调度参数保存即校验** —— 非法 cron / 周期在保存时就被 400 拒绝，界面上有实时预览（`POST /api/rules/schedule-preview`，与保存校验同一条代码路径）。

## 快速启动（Docker，推荐）

```bash
# 1. 配置环境变量
cp backend/.env.example .env
#    编辑 .env，填入所有必填密钥（SECRET_KEY / JWT_SECRET_KEY /
#    MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD / ES_PASSWORD）

# 2. 启动容器栈（mysql + backend + frontend）
docker compose up -d

# 3. 初始化业务表（首次）
docker compose exec backend python scripts/create_scripts_table.py

# 4. 访问
open http://localhost
```

compose 起的是三个独立容器：`sec-mysql` / `sec-backend` / `sec-frontend`。调度器在 `sec-backend` 内与 Web 并行启动，无需额外配置。

> 另有单体容器部署方式（`security-dashboard-v2`：ubuntu:22.04 + mysqld + nginx + uvicorn + run_scheduler 四合一），用 `./scripts/deploy.sh [backend|frontend|migrate|all]` 增量同步代码。详见脚本文件头的踩坑记录。

### 环境变量

完整列表见 **[backend/.env.example](backend/.env.example)**。几个容易踩的：

| 变量 | 说明 |
|------|------|
| `ALLOW_INSECURE_DEFAULTS` | **生产必须 0**。置 1 允许占位密钥通过启动校验，等于公开 JWT 签名密钥 |
| `MYSQL_HOST` | compose 下必须是服务名 `mysql`，不是 `localhost` |
| `MYSQL_PASSWORD` | 留空会让后端**静默改用 SQLite**（`backend/data/security.db`），表现为连的 MySQL 看不到数据、登录 401 |
| `TRUSTED_PROXY_HEADERS` | 仅在 API 前有可信 nginx 时置 1 |
| `COOKIE_SECURE` | 仅 HTTPS 部署置 1 |

验证后端实际连的库：

```bash
cd backend && python -c "from app.core.config import settings; print(settings.USE_SQLITE, settings.database_url)"
# 期望：False mysql+pymysql://...
```

## 手动部署（不使用 Docker）

### 环境要求

| 组件 | 版本 |
|------|------|
| Python | ≥ 3.10 |
| Node.js | ≥ 18 |
| MySQL | ≥ 8.0（5.7 也可，需调整字符集） |
| Elasticsearch | 8.x（外部服务） |

### 1. 初始化数据库

```sql
CREATE DATABASE security_dashboard DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'your_mysql_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON security_dashboard.* TO 'your_mysql_user'@'%';
FLUSH PRIVILEGES;

-- 建表 + 默认配置 + 初始管理员
SOURCE docs/mysql_init_dashboard.sql;
```

### 2. 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp ../backend/.env.example .env   # 填入真实值
python scripts/create_scripts_table.py

# Web 服务（生产建议交给 systemd）
uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1

# 调度器是独立进程，需另起
python run_scheduler.py
```

> ⚠️ 两个进程缺一不起：只起 uvicorn 时规则永远不会自动执行；只起 `run_scheduler.py` 时没有 API。

### 3. 前端

```bash
cd frontend
npm install
npm run dev      # 开发，http://localhost:5173
npm run build    # 生产，产物在 dist/
```

### 4. Nginx

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;   # dist 内容
    index index.html;

    # Vue Router **history** 模式必须有这条兜底
    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # 这两行对 PUT/POST 至关重要，不可省略 —— 否则地址编辑会被 422 拒绝
        proxy_set_header Content-Type $content_type;
        proxy_set_header Content-Length $content_length;
    }

    # 可选：Prometheus 抓取入口
    location /metrics {
        proxy_pass http://127.0.0.1:5000/metrics;
    }
}
```

### 5. systemd

**Web** — `/etc/systemd/system/sec-backend.service`

```ini
[Unit]
Description=Security Dashboard Backend
After=network.target mysql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/security-dashboard/backend
EnvironmentFile=/opt/security-dashboard/backend/.env
ExecStart=/opt/security-dashboard/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**调度器** — `/etc/systemd/system/sec-scheduler.service`

```ini
[Unit]
Description=Security Dashboard Scheduler
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/security-dashboard/backend
EnvironmentFile=/opt/security-dashboard/backend/.env
ExecStart=/opt/security-dashboard/backend/venv/bin/python run_scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sec-backend sec-scheduler
```

`run_scheduler.py` 已处理 SIGTERM（会调 `scheduler_service.stop()` 收线程池）。

## 项目结构

```
security-dashboard/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由（rules / alerts / addresses / inspect / remote / ...）
│   │   ├── core/           # config、权限矩阵（permissions.py）、密码策略
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── schemas/        # Pydantic schema
│   │   ├── services/       # rule_runner / rule_executor / scheduler_service / es_service ...
│   │   └── utils/          # 时区等
│   ├── migrations/         # 幂等 SQL 迁移（见 docs/migrations.md）
│   ├── scripts/            # 初始化脚本
│   ├── tests/              # pytest 回归（338 项）
│   ├── .env.example        # 环境变量模板
│   └── run_scheduler.py    # 独立调度器进程
├── frontend/
│   └── src/
│       ├── views/          # 页面组件
│       ├── components/     # 布局与共用组件
│       ├── api/            # axios 封装与接口定义
│       ├── store/          # Pinia（user / ui）
│       ├── config/         # 角色标签等展示用常量
│       └── router/         # 路由（hash 模式）
├── docs/                   # 设计文档、迁移说明、基线 SQL
├── scripts/
│   ├── deploy.sh           # 增量同步进单体容器
│   └── check_mysql_schema.sql  # 库表结构体检（缺表/缺列/类型不符）
└── docker-compose.yml
```

## 数据库迁移

建表用 `Base.metadata.create_all()`，它**只补缺失的表，不会给已有表补列**。给模型加字段时必须同时在 `backend/migrations/` 放一份幂等 SQL，并在 **[docs/migrations.md](docs/migrations.md)** 登记。

```bash
# 单体容器
./scripts/deploy.sh migrate

# compose
docker compose exec -T mysql mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" security_dashboard \
  < backend/migrations/<文件名>.sql
```

> **给模型加字段时的三步**（漏第二步就是「表在、列没了」）：
> 1. 改 `app/models/` 下的模型；
> 2. 在 `backend/migrations/` 放一份幂等 `ALTER`，并在 `docs/migrations.md` 登记；
> 3. 在 `scripts/check_mysql_schema.sql` 的 `_sc_expect` 里补一行 —— 否则下一体检会误报。
>
> 旧库升上来后拿[库表结构体检](#库表结构体检)核对一遍。

## 库表结构体检

`scripts/check_mysql_schema.sql` —— 把线上库的真实结构（`information_schema`）跟当前模型快照对一遍，抓**旧版本升上来之后的缺表 / 缺列 / 类型不符**。

```bash
# Docker 单体容器
docker exec -i security-dashboard-v2 sh -c \
  'set -a; . /opt/security-dashboard/backend/.env; set +a; \
   mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' \
  < scripts/check_mysql_schema.sql

# 手动部署 / 任何能连上 MySQL 的机器
cd /opt/security-dashboard
set -a; . backend/.env; set +a
mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
  < scripts/check_mysql_schema.sql

# 或进 mysql 交互式里 source（路径写绝对路径）
mysql -u<user> -p security_dashboard
mysql> source /opt/security-dashboard/scripts/check_mysql_schema.sql
```

输出五个结果集：

| 结果集 | 含义 |
|--------|------|
| ① 缺表 | 整张表没有 |
| ② 缺列 | `create_all()` 补不了，必须 `ALTER` —— **最常见的升级事故** |
| ③ 类型不符 | 老字段类型跟现在对不上（只提示，`MODIFY` 会动已有数据） |
| ④ 补齐脚本 | 按「先建表 → 再加列 → 最后改类型」排好序，可直接拷去执行 |
| ⑤ 结论 | 三个数字全是 0 就说明结构对得上 |

**安全性**：纯 SQL。业务表只通过 `information_schema` 读**结构元数据**，不读不改业务数据；写操作只落在 `_sc_*` 中间表上，跑完自删。账号需要该库的 `CREATE` / `DROP` 权限（README 那种 `GRANT ALL PRIVILEGES ON security_dashboard.*` 的账号没问题）。

**维护**：模型加了字段就在 `_sc_expect` 里补一行，共 6 列：

```sql
(表名, 列名, MySQL类型, 类型族, 是否NOT NULL, 是否主键)
-- 例：('rule_execution_logs','duration_ms','INT','int',0,0)
```

类型族只用于比对，取值 `int` / `bool` / `float` / `str` / `text` / `datetime` / `date` / `time` / `json` / `blob`。刻意不比类型字符串 —— `BOOL` 在 MySQL 里是 `tinyint(1)`，`MEDIUMTEXT` / `TEXT` 都算 `text`。

## 测试

后端 pytest 回归（338 项）覆盖鉴权、密码策略、三权分立、权限矩阵勾选分配、脚本执行闸门、ingest 令牌、调度参数校验与执行日志留痕：

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

测试跑在 SQLite 内存库上，不需要 MySQL / Elasticsearch。`conftest.py` 自己设置 `ALLOW_INSECURE_DEFAULTS=1`、`USE_SQLITE=1` 与占位密钥 —— **仅供测试，不要在命令行手动加 `ALLOW_INSECURE_DEFAULTS=1`**。

前端：

```bash
cd frontend
npm run lint    # ESLint
npm run build
```

## 监控接入（/metrics）

`GET /metrics` 输出 Prometheus 文本格式，**手写实现，不引 `prometheus_client`**。指标只含计数与耗时，不吐规则名 / 查询语句（避免基数爆炸和信息泄露）。

| 指标 | 类型 | 含义 |
|------|------|------|
| `scheduler_up` | gauge | 调度器心跳是否新鲜（1=是） |
| `scheduler_heartbeat_age_seconds` | gauge | 进程心跳距今秒数 |
| `scheduler_last_activity_age_seconds` | gauge | 最近一次任务跑完距今秒数 |
| `scheduler_jobs` | gauge | 已排期任务数（含内置 retention） |
| `scheduler_stale_rules` | gauge | `next_run` 已过期的规则数 |
| `rule_runs_24h{status}` | gauge | 近 24h 执行次数，按 success/error/missed 分 |
| `rule_missed_24h` | gauge | 近 24h 漏跑次数 |
| `rule_last_success_timestamp{rule_id}` | gauge | 最近一次成功执行的时间戳 |
| `rule_last_run_duration_seconds{rule_id}` | gauge | 最近一次执行耗时 |
| `rule_consecutive_failures{rule_id}` | gauge | 连续失败次数 |

**鉴权**：在「系统设置 → 安全设置」填了 `metrics_token` 后，抓取需带 `?token=<值>`（否则 401/403）；留空则开放，适合内网抓取。

## 初始账号

首次初始化的数据库会带一个管理员（**登录后请立即改密**）：

| 字段 | 值 |
|------|-----|
| 账号 | `admin` |
| 密码 | `ChangeMe2026` |

> 系统**不会**强制首次登录改密，需自行在「用户管理 → 重置密码」完成。
>
> 密码策略（`app/core/policy.py`）：至少 8 位、同时含字母和数字，拒绝常见弱口令（`admin123`、`12345678`、`changeme` 等）。不满足的密码在建号 / 改密时被直接拒绝并返回具体中文原因。
>
> 只影响**新初始化**的库。已有库的账号和密码哈希不变。
>
> 旧库里角色叫 `admin` 的账号，启动时自动升级为 `sys_admin`。这意味着它会**失去** `audit`（日志中心）和 `manage_authz`（改角色）—— 那两把钥匙按三权分立应分给审计管理员和安全管理员。

## 告警规则说明

规则支持多阶段聚合：

- **Stage 1** — 时间窗口内聚合（如 5 分钟内同一 IP 的 404 请求 ≥ 50 次）
- **Stage 2** — 跨索引关联分析（取攻击目标域名）
- **Stage 3** — 二次聚合统计

触发后按模板渲染 `{src_ip}`、`{stage1.count}` 等占位符写入告警。

### 过滤条件逻辑运算

```json
{
  "logic": "and",
  "filters": [
    {"field": "src_ip", "operator": "not_equals", "value": "127.0.0.1"},
    {
      "logic": "or",
      "filters": [
        {"field": "status", "operator": "equals", "value": "404"},
        {"field": "status", "operator": "equals", "value": "500"}
      ]
    }
  ]
}
```

运算符：比较（等于/不等于/大于/大于等于/小于/小于等于）、文本（包含/不包含/开头是/结尾是）、存在（存在/不存在）、其他（IN、BETWEEN）。

### 调度方式

| 执行方式 | 取值 | 示例 |
|----------|------|------|
| 手动执行 | `once` | — |
| 周期执行 | `interval` | `5 minutes` / `2 hours` / `1 days` |
| Cron | `cron` | `0 9 * * *`（分 时 日 月 周） |

表单里有实时排期预览；保存前会再校验一次，非法表达式无法存库。

## 效果图

<img width="1868" height="778" alt="image" src="https://github.com/user-attachments/assets/4bc84414-30f1-43b9-9fd9-b90e971558f7" />

<img width="1884" height="614" alt="image" src="https://github.com/user-attachments/assets/a438dbd7-8fce-4077-b82a-7ecd1518c2da" />

<img width="1865" height="634" alt="image" src="https://github.com/user-attachments/assets/3a757f86-3f6a-4fd0-a246-03f5140c72d3" />

<img width="1873" height="634" alt="image" src="https://github.com/user-attachments/assets/7d99932a-4a47-4ea6-97bb-3d5baeafdef1" />
