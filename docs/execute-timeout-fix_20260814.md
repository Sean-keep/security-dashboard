# 规则执行(execute)超时修复 + Rule 13 恢复

## 目标
1. 给出现有 id=3 规则(高频攻击IP检测)的完整 SQL，供用户手动调整
2. 修复规则 execute 接口 180s 超时问题，使规则能真正执行写入

## 根因定位
- ES 聚合本身极快(0.41s)，返回 **100 条** IP(30分钟内请求>5次的 src_ip)
- `rule_executor.py::_write_mysql` 逐条循环对每条 IP 调 `_lookup_country_single(ip)` 查国家(ipinfo.io, 0.62s/IP)
- 100 条 × 0.62s ≈ 62s，加上 MySQL upsert + ipinfo 偶发慢 → 累积超过 180s 超时
- 历史"写入4条/次"能正常工作，是因为历史结果少、查国家快(非系统 bug，是数据量变化)

## 修复方案
`backend/app/services/rule_executor.py` 的 `_write_mysql`：
- 循环前先收集去重 IP 列表
- 用 `ThreadPoolExecutor(max_workers=10)` **并发**查国家，结果存 `_country_cache` dict
- 循环写 MySQL 时从缓存取 country(不再逐条串行查)

## 验证结果(容器内)
- 修改前：execute 180s 超时(ReadTimeout)
- 修改后：`POST /api/rules/3/execute` 仅 **5.8s** 完成
- 100 条记录，写入 100 条地址 + 100 条告警(status 200)
- 已 docker cp 进 sec-backend 容器并 restart，编译通过

## 关于"写入条数"的控制
- `es_service.execute_multi_stage_rule(stages, output_mapping, limit=100)`：limit 是方法参数默认 100，stage 配置**无** per-stage limit 字段
- 当前 having>5 → 100 个 IP(已达 100 上限)
- 若想回到历史"4条/次"节奏：
  - 方案A：在 SQL 的 aggregation.having 调高阈值(如 "gt": 800，当前数据仅 top 4 超此值)
  - 方案B：给 es_service 加 per-stage "limit" 字段支持(需改代码+同步容器，待用户确认)

## 当前状态
- id=3 规则 SQL 已导出(docs/rule3_insert.sql 为用户基线，不含 id，执行会新建；或用户改后 UPDATE id=3)
- execute 超时已修复(系统层，对所有规则生效)
- rule_executor.py 改动**未提交 git**(按用户"测试完成后再上传"原则)

## 待用户操作
1. 修改规则 SQL(having/limit/create_alert 等)后执行
2. 告知是否需要加 per-stage "limit" 严格 top-N 支持
3. 改完规则后告知，重新验证 execute
