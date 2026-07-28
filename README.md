# Security Dashboard V2

安全监控平台——FastAPI + Vue 3 + MySQL + Elasticsearch。

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

## 功能模块

- **攻击地址管理** — 实时封禁 IP，自动查询归属地
- **规则引擎** — 多阶段聚合规则，支持跨索引关联分析
- **告警管理** — 模板渲染、统计趋势、批量处理
- **安全巡检** — 定时任务、脚本执行、巡检报告生成导出
- **系统设置** — ES/MySQL/Grafana 连接配置、用户管理、操作日志

## ⚡ 云端预览 (GitHub Codespaces)

无需本地安装任何依赖，直接在 GitHub 上启动完整开发环境：

1. 点击本仓库页面右上角 **Code** → **Codespaces** → **Create codespace on main**
2. 等待环境自动初始化（约 3-5 分钟）
3. 在 `backend/` 目录创建 `.env` 文件（参考 `.env.example`）
4. 启动后端：`cd backend && uvicorn app.main:app --host 0.0.0.0 --port 5000`
5. 启动前端（dev 模式）：`cd frontend && npm run dev`
6. 点击弹出的端口预览链接即可访问

> ⚠️ Codespaces 默认无 MySQL/ES，需要在 `backend/.env` 中配置外部数据源。

## 快速启动

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
