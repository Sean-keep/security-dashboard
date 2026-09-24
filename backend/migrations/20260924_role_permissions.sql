-- 角色权限矩阵：从「内置写死」改成系统管理员可勾选分配。
--
-- 默认值与 app/core/permissions.py 的 ROLE_PERMISSIONS 一致。只补缺失行，
-- 不覆盖已有勾选 —— 跑多少遍都安全。
--
-- 三权互斥（一个角色不能同时握两项三权、每项三权只认一个在任者、每项三权
-- 必须有人接）在 PUT /settings/permissions 的保存路径上校验，不在表结构里
-- 表达 —— 表只负责存。

CREATE TABLE IF NOT EXISTS role_permissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role VARCHAR(32) NOT NULL,
    permissions TEXT,
    updated_at DATETIME NULL,
    updated_by VARCHAR(64) DEFAULT '',
    UNIQUE KEY uk_role_permissions_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO role_permissions (role, permissions, updated_by) VALUES
    ('sys_admin',   'manage_accounts,manage_system,operate', 'seed'),
    ('sec_admin',   'manage_authz,operate',                  'seed'),
    ('audit_admin', 'audit',                                 'seed'),
    ('operator',    'operate',                               'seed'),
    ('viewer',      '',                                      'seed');
