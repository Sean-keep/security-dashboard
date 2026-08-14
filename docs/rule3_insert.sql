INSERT INTO rules (name,description,stages,output_mapping,es_index,schedule_type,schedule_value,is_enabled,actions,created_by)
VALUES (
  '高频攻击IP检测',
  '检测30分钟内请求频率超过5次的攻击源IP，自动写入攻击地址库并生成告警',
  '[{"id": "stage1", "index": "online*nginx*", "time_window": {"minutes": 30}, "filters": [], "aggregation": {"group_by": ["src_ip"], "metric": "count", "alias": "count", "having": {"operator": "gt", "value": 5}}, "join": null}]',
  '{"ip_address": {"from_stage": "stage1", "field": "src_ip"}, "attack_count": {"from_stage": "stage1", "field": "count"}}',
  'online*nginx*',
  'interval',
  '10 minutes',
  '1',
  '[{"type": "write_mysql", "table": "addresses", "mapping": {}, "severity": "medium"}, {"type": "create_alert", "template": "检测到高频攻击IP {ip_address}，30分钟内请求 {attack_count} 次", "title_template": "高频攻击IP: {ip_address}", "severity": "high", "severity_conditions": []}]',
  '1'
);