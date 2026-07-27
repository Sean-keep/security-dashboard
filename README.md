# Security Dashboard V2

安全态势监控平台——FastAPI + Vue 3 + MySQL + Elasticsearch。

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

## 快速启动

```bash
# 1. 启动容器栈
docker-compose -f docker-compose.yml up -d

# 2. 进入后端容器初始化数据库
docker exec sec-backend python scripts/create_scripts_table.py

# 3. 访问前端
open http://localhost
# 登录账号: admin / 123456
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
│   └── Dockerfile
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

系统默认连接外部 Elasticsearch 数据源（需在「系统设置」中配置）：

- Host: `35.241.110.62:9200`
- Index Pattern: `online*nginx*`
- 认证: Basic Auth (elastic)

## 告警规则说明

规则支持多阶段聚合，示例 Rule 13「高频攻击 IP 检测」：

- **Stage 1**: 5 分钟内同一 IP 404 请求 ≥ 50 次
- **Stage 2**: 获取攻击目标域名
- **Stage 3**: 聚合总请求数

规则触发后自动写入告警，通过模板渲染 `{攻击地址}`、`{攻击域名}` 等占位符。

## 巡检报告

支持按日期生成 Word / TXT 格式巡检报告，包含：

- 攻击地址统计（Top 攻击次数）
- 服务器监控指标（CPU / 内存 / 磁盘）
- 自定义脚本执行结果
