-- 三权分立 + 界面外观配置
--
-- 旧模型 admin/operator/viewer：admin 一个人握着账号管理、授权、审计三把钥匙，
-- 正是三权分立要拆开的东西。这里把 admin 迁成 sys_admin（账号+系统配置+业务），
-- 授权与审计需要另外建号。
--
-- operator / viewer 语义没变，不动。
--
-- 幂等：重复执行安全。app 启动时的 _migrate_legacy_roles() / _seed_system_config()
-- 也会做同样的事，两边都做是因为一个管已有部署、一个管全新库。

-- 1) 旧角色 → 新角色
UPDATE `users` SET `role` = 'sys_admin' WHERE `role` = 'admin';

-- 2) 界面外观默认值（UI 管理）。INSERT IGNORE 靠 key 唯一索引去重。
INSERT IGNORE INTO `system_config` (`key`, `value`, `label`, `description`, `group_name`) VALUES
  ('ui_theme',           'light',          '主题模式',        'light 或 dark',                          'ui'),
  ('ui_primary_color',   '#409eff',        '主色',            'Element Plus 主色（十六进制）',          'ui'),
  ('ui_density',         'default',        '表格密度',        'default / small / large',                'ui'),
  ('ui_sidebar_collapse','false',          '侧边栏默认折叠',  'true 或 false',                          'ui'),
  ('ui_site_title',      '安全巡检平台',   '站点标题',        '侧边栏左上角显示的名称',                 'ui');
