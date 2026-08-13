# Security Dashboard V2

安全监控平台——FastAPI + Vue 3 + MySQL + Elasticsearch。

> **支持容器部署（推荐）和手动部署两种方式**，详见下方说明。

初衷：巡检可视化

前置：日志范式化，目前使用的是logstash（nginx日志解析配置如下）

grok {

    match => [
    
       "message",'(?<log_time>\S+\s\S+).*\[PID:(?<PID>\S+)\]\s\[(?<id>\S+)\]\s\[(?<name>\S+)\]\s\S\s(?<level>\S+)(?<msg>.*)',
       
       "message",'(?<log_time>\S+\s\S+)\s(?<level>\S+)\s(?<msg>.*)'
       
          ]
          
    }

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Element Plus + ECharts |
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | MySQL 8 + Elasticsearch 8 |
| 部署 | Docker + Docker Compose |

## ⚡ 在线体验 (GitHub Codespaces)

无需本地安装任何依赖，直接在 GitHub 上启动完整开发环境：

1. 点击本仓库右上角 **Code** → **Codespaces** → **Create codespace on main**
2. 等待环境自动初始化（约 3-5 分钟）
3. 在 `backend/` 目录创建 `.env` 文件（参考 `.env.example`），填入 MySQL 和 ES 地址
4. 启动后端：`cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 5000`
5. 启动前端（dev 模式）：`cd frontend && npm run dev`
6. 点击弹出的端口预览链接即可访问

> ⚠️ Codespaces 默认无 MySQL/ES，需在 `backend/.env` 中配置外部数据源。

## 功能模块

- **攻击地址管理** — 实时封禁 IP，自动查询归属地
- **规则引擎** — 多阶段聚合规则，支持跨索引关联分析
- **告警管理** — 模板渲染、统计趋势、批量处理
- **安全巡检** — 定时任务、脚本执行、巡检报告生成导出
- **系统设置** — ES/MySQL/Grafana 连接配置、用户管理、操作日志

## 手动部署（不使用 Docker）

### 环境要求

| 组件 | 版本要求 |
|------|----------|
| Python | ≥ 3.10 |
| Node.js | ≥ 18 |
| MySQL | ≥ 8.0（也可使用 5.7，需调整字符集配置） |
| Elasticsearch | 8.x（外部服务，需提供地址） |

### 1. 初始化数据库

```sql
CREATE DATABASE security_dashboard DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'your_mysql_user'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON security_dashboard.* TO 'your_mysql_user'@'%';
FLUSH PRIVILEGES;
```

### 2. 后端部署

```bash
cd backend

# 创建虚拟环境
python -m venv venv
# Linux/macOS
source venv/bin/activate
# Windows PowerShell
venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 初始化数据库表（首次执行）
python scripts/create_scripts_table.py

# 启动 Web 服务（前台运行，生产环境建议用 systemd 管理）
uvicorn app.main:app --host 0.0.0.0 --port 5000 --workers 1
```

> ⚠️ 调度器（定时执行告警规则）默认不随 Web 服务自动启动，需额外执行：
> ```bash
> python run_scheduler.py
> ```
> 推荐通过 systemd 或 Windows 任务计划程序将其作为后台服务运行。

### 3. 前端部署

#### 开发模式

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

> ⚠️ 开发模式下前端请求默认发往 `http://localhost:5000/api`（后端地址），如后端端口不同，修改 `frontend/src/api/index.js` 中的 `baseURL`。

#### 生产构建

```bash
cd frontend
npm install
npm run build
# 产物输出到 frontend/dist/
```

### 4. 前端生产部署（Nginx 配置）

将 `dist/` 下的文件放入 Nginx 可访问目录，参考以下配置：

```nginx
# /etc/nginx/conf.d/security-dashboard.conf

server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;   # dist 目录路径
    index index.html;

    # 前端路由（Vue Router history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # 以下两行对 PUT/POST 请求至关重要，不可省略
        proxy_set_header Content-Type $content_type;
        proxy_set_header Content-Length $content_length;
    }
}
```

> ⚠️ `proxy_set_header Content-Type` 和 `Content-Length` 两行**必须保留**，否则 PUT 请求（如地址编辑）会被后端以 422 拒绝。

重载 Nginx 配置：

```bash
nginx -t && nginx -s reload
```

### 5. 环境变量配置

所有配置通过 `backend/.env`（容器）或系统环境变量传入，参考 `backend/.env.example`：

```bash
# 数据库
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=security_dashboard

# JWT（请使用随机字符串，至少 32 字符）
SECRET_KEY=your-secret-key-min-32-chars
JWT_SECRET_KEY=your-jwt-secret-key

# Elasticsearch（外部服务）
ES_HOST=your-es-host
ES_PORT=9200
ES_SCHEME=https
ES_USER=elastic
ES_PASSWORD=your_es_password
ES_INDEX=online*nginx*    # ES 索引通配符，按实际填写
ES_VERIFY_CERTS=false
```

> ⚠️ **手动部署必看**：
> - `backend/.env` 必须通过 `python-dotenv` 加载（`requirements.txt` 已包含）。若启动时 `.env` 未被读取，`MYSQL_PASSWORD` 会落到空值，后端将**自动改用 SQLite**（`backend/data/security.db`），导致你连的 MySQL 看不到任何数据、登录 401。
> - 确保 `MYSQL_PASSWORD` 为**非空真实密码**，且 `.env` 放在 `backend/` 目录下、在 `backend/` 目录启动 uvicorn。
> - 验证后端实际连接的库：`cd backend && python -c "from app.core.config import settings; print(settings.USE_SQLITE, settings.database_url)"`（`USE_SQLITE=False` 且 URL 为 `mysql+...` 才正确）。

### 6. systemd 服务配置示例（Linux）

**Web 服务**：`/etc/systemd/system/sec-backend.service`

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

**调度器**：`/etc/systemd/system/sec-scheduler.service`

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

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable sec-backend sec-scheduler
sudo systemctl start sec-backend sec-scheduler
```

### 目录结构（手动部署建议）

```
/opt/security-dashboard/
├── backend/
│   ├── app/
│   ├── scripts/
│   ├── .env                  # 环境变量（不要提交到 Git）
│   ├── requirements.txt
│   ├── run_scheduler.py
│   └── venv/                 # Python 虚拟环境
├── frontend/
│   ├── src/
│   ├── dist/                 # npm run build 产物
│   └── nginx.conf            # 前端构建时可复用的参考配置
└── nginx/
    └── conf.d/
        └── security-dashboard.conf
```

## 快速启动（Docker 部署，推荐）

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入真实配置

# 2. 启动容器栈
docker-compose -f docker-compose.yml up -d

# 3. 进入后端容器初始化数据库
docker exec sec-backend python scripts/create_scripts_table.py

# 4. 访问前端
open http://localhost
```

> 💡 **调度器**（定时执行告警规则）在容器内通过 `run_scheduler.py` 与 Web 服务并行启动，无需额外配置。

## 项目结构

```
security-dashboard-v2/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # API 路由（rules, alerts, addresses, inspect, reports...）
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── schemas/      # Pydantic schema
│   │   └── services/     # 核心服务（ES 查询、规则执行、调度器、巡检）
│   ├── scripts/          # 初始化脚本
│   ├── Dockerfile
│   └── .env.example      # 环境变量模板
├── frontend/             # Vue 3 前端
│   ├── src/
│   │   ├── views/        # 页面组件
│   │   ├── api/          # API 调用
│   │   └── router/       # 路由配置
│   └── Dockerfile
├── docs/                 # 设计文档
├── fixes/                # 修复记录
└── docker-compose.yml     # 容器编排
```

## 数据源配置

系统默认连接外部 Elasticsearch 数据源（需在「系统设置」中配置，或通过环境变量传入）：

- Host: `ES_HOST`
- Index Pattern: `ES_INDEX`（默认 `online*nginx*`）
- 认证: Basic Auth（`ES_USER` / `ES_PASSWORD`）

## 初始账号

默认管理员账号（首次启动后请立即修改密码）：

| 字段 | 值 |
|------|-----|
| 账号 | admin |
| 密码 | （首次登录后强制修改）|

## 告警规则说明

规则支持多阶段聚合，支持：

- **Stage 1**: 时间窗口内聚合（如 5 分钟内同一 IP 404 请求 ≥ 50 次）
- **Stage 2**: 跨索引关联分析（获取攻击目标域名）
- **Stage 3**: 二次聚合统计

规则触发后自动写入告警，通过模板渲染 `{攻击地址}`、`{攻击域名}` 等占位符。

## 巡检报告

支持按日期生成 Word / TXT 格式巡检报告，包含：

- 攻击地址统计（Top 攻击次数）
- 服务器监控指标（CPU / 内存 / 磁盘，需配置 Grafana + Prometheus 数据源）
- 自定义脚本执行结果

## 效果图

<img width="1868" height="778" alt="image" src="https://github.com/user-attachments/assets/4bc84414-30f1-43b9-9fd9-b90e971558f7" />

<img width="1884" height="614" alt="image" src="https://github.com/user-attachments/assets/a438dbd7-8fce-4077-b82a-7ecd1518c2da" />

<img width="1865" height="634" alt="image" src="https://github.com/user-attachments/assets/3a757f86-3f6a-4fd0-a246-03f5140c72d3" />

<img width="1873" height="634" alt="image" src="https://github.com/user-attachments/assets/7d99932a-4a47-4ea6-97bb-3d5baeafdef1" />
