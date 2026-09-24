/**
 * 角色 / 权限点 —— 与后端 app/core/permissions.py 一一对应。
 *
 * 这里只是**展示侧**的副本（中文名、标签色、说明文案）。真正的授权判断以
 * 后端返回的 `permissions` 数组为准：前端显隐按钮只为好看，越权一律由后端挡。
 *
 * 三权分立：账号管理 / 授权 / 审计 三项各自独占一个角色，没有任何角色能
 * 同时持有两项。矩阵本身可由系统管理员在线勾选分配，但这三条底线勾不破。
 */

export const ROLES = ['sys_admin', 'sec_admin', 'audit_admin', 'operator', 'viewer']

export const ROLE_LABELS = {
  sys_admin: '系统管理员',
  sec_admin: '安全管理员',
  audit_admin: '审计管理员',
  operator: '业务操作员',
  viewer: '只读用户',
}

export const ROLE_TAGS = {
  sys_admin: 'danger',
  sec_admin: 'warning',
  audit_admin: 'success',
  operator: 'primary',
  viewer: 'info',
}

export const ROLE_DESCRIPTIONS = {
  sys_admin: '账号增删禁用、系统配置、远程接口；可做日常安全业务。不能改角色，不能看审计。',
  sec_admin: '角色授权（改用户角色）+ 安全策略与日常业务。不能建号删号，不能看审计。',
  audit_admin: '只看审计（登录 / 操作日志）。不能改系统，不能授权，不能改安全策略。',
  operator: '日常安全业务：写日报、处置告警、维护地址与规则。无任何管理权。',
  viewer: '只读。可看仪表盘、列表、报告，不能写。',
}

export const ROLE_OPTIONS = ROLES.map(r => ({ value: r, label: ROLE_LABELS[r], description: ROLE_DESCRIPTIONS[r] }))

/**
 * 权限点定义。`power: true` 的三项就是「三权」，界面上单独成组展示。
 * 顺序与后端 PERMISSIONS 元组一致。
 */
export const PERMISSION_DEFS = [
  { name: 'manage_accounts', label: '账号管理', power: true,  desc: '建号、删号、禁用、重置密码、改昵称。**不含改角色。**' },
  { name: 'manage_authz',    label: '授权',     power: true,  desc: '修改用户角色。这是「授权」那把钥匙。' },
  { name: 'audit',           label: '审计',     power: true,  desc: '查看登录日志与操作日志。' },
  { name: 'manage_system',   label: '系统配置', power: false, desc: '系统配置、远程接口、脚本库、任意代码执行、指标与别名。' },
  { name: 'operate',         label: '安全业务', power: false, desc: '规则、告警、地址、日报生成与删除、脚本执行、发送方认人。' },
]

/**
 * 角色 → 权限点的**内置默认**，仅作拉取前的兜底展示。
 *
 * 事实来源是后端 `role_permissions` 表 —— 系统管理员在权限管理页勾选分配后
 * 以库里那份为准（`GET /settings/permissions` 会回 `roles` 和 `defaults`）。
 * 这份副本的漂移不影响鉴权，只影响还没拉到后端矩阵那一瞬间的显示。
 */
export const ROLE_PERMISSIONS = {
  sys_admin: ['manage_accounts', 'manage_system', 'operate'],
  sec_admin: ['manage_authz', 'operate'],
  audit_admin: ['audit'],
  operator: ['operate'],
  viewer: [],
}

export const roleLabel = (r) => ROLE_LABELS[r] || r
export const roleTag = (r) => ROLE_TAGS[r] || 'info'
