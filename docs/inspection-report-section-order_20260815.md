# 巡检报告板块顺序可调整 + 勾选下放到面板

**日期**：2026-08-15
**文件**：`frontend/src/views/InspectionReport/index.vue`

## 改动
1. 「包含当日攻击地址」「包含服务器监控」两个勾选从工具栏（toolbar）下移到面板顶部（`.pick-checks`），面板不再依赖脚本/端口是否存在才显示（去掉 `v-if`）。
2. 面板底部新增「报告板块顺序（从上到下）」排序区：四个板块（当日攻击地址 / 服务器监控 / 脚本执行结果 / 接收数据（最近一条））各带「↑上移 / ↓下移」按钮。
3. 新增 `sectionOrder` ref（`['addresses','monitoring','scripts','ingested']`）+ `moveUp/moveDown` + `sectionLabels`，顺序持久化到 localStorage（`report_section_order`），onMounted 恢复。
4. 生成报告页内容区、预览弹窗的 4 个板块，统一改为 `<template v-for="key in sectionOrder">` 循环渲染（按 `key` 命中对应板块 + 原 enabled 条件）。
5. `buildText` / `buildHtml`（TXT/Word 导出）改为按 `sectionOrder` 顺序输出。
6. 补充样式：`.pick-checks / .pick-div / .order-box / .order-title / .order-item / .order-name / .order-btns`。

## 构建与部署
- `npm run build` 成功（`built in 24.33s`，仅 chunk>500kB 警告，无编译错误），新指纹 `index-CD5VinQT.js`。
- 部署到 `sec-frontend` 容器：用 `docker cp "frontend\dist\." sec-frontend:/usr/share/nginx/html/` 复制（单层，避免历史双层 assets 问题）。
- 验证：容器内 `index.html` 引用 `/assets/index-CD5VinQT.js`；单层 JS 含 `报告板块顺序`/`order-box`/`上移` 文本（确认逻辑已编译进去）。
- 无需重启容器（nginx 静态文件实时生效）。

## 注意
- 删除容器内旧 `assets` 目录被安全策略二次确认拦截（聊天文字确认不生效），改用「直接覆盖复制」方案，旧 `index-*.js`（如 CT9ezPSz/DStlv6vT 等）作为孤儿文件残留在容器内 `/usr/share/nginx/html/assets/`，不影响功能（index.html 只引用当前指纹）。如需彻底清理，待用户在交互弹窗确认删除后执行 `docker exec sec-frontend rm -rf /usr/share/nginx/html/assets` 再重 cp。

## 待办
- 浏览器硬刷新（Ctrl+Shift+R）确认排序 UI 与板块顺序生效。
- 本次改动尚未 git 提交/推送（工作区有未提交改动）。
