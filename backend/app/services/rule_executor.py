import json
from datetime import datetime
from sqlalchemy import text as sa_text
from app.models.address import Address
from app.models.alert import Alert
from app.models.rule import Rule
from app.models.execution_log import RuleExecutionLog
from app.api.addresses import _lookup_country_single


def record_execution_log(db, rule_id, rule_name="", alert_count=0, detail=None,
                         status="success", error_message=None):
    """创建一条规则执行记录。
    使用 raw SQL 写入，避免 ORM 表缓存导致 detail 列不可用。
    detail 可传 dict（自动序列化为 JSON 字符串）或字符串。
    """
    try:
        if isinstance(detail, (dict, list)):
            detail_str = json.dumps(detail, ensure_ascii=False, default=str)
        else:
            detail_str = detail or ""
        db.execute(
            sa_text(
                """INSERT INTO rule_execution_logs
                   (rule_id, rule_name, executed_at, alert_count, detail, status, error_message)
                   VALUES (:rule_id, :rule_name, :executed_at, :alert_count, :detail, :status, :error_message)"""
            ),
            {
                "rule_id": rule_id,
                "rule_name": rule_name or "",
                "executed_at": datetime.now(),
                "alert_count": alert_count or 0,
                "detail": detail_str,
                "status": status,
                "error_message": error_message
            }
        )
        db.commit()
        return True
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[RuleExecutor] Failed to record execution log: {e}")
        return None


def render_alert_template(template: str, result: dict, output_mapping: dict = None) -> str:
    """Render alert template by replacing {field} placeholders.
    
    Supports:
    - Simple field: {field_name}  →  result.get(field_name) or fallback
    - Stage field: {stage.field}  →  result._stages[stage][0].field
    
    Fallback: if {field_name} not found but output_mapping maps it to an English
    field name, use the English key value (handles reverse_output_mapping side-effect).
    """
    if not template:
        return ""
    import re as _re

    # Build reverse map: Chinese key → English key
    # Also support _output_mapping injected by reverse_output_mapping()
    _om = output_mapping or result.get("_output_mapping")
    reverse_map = {}
    if _om:
        for out_name, mapping_info in _om.items():
            if isinstance(mapping_info, dict):
                f = mapping_info.get("field", "")
            else:
                f = str(mapping_info)
            if f:
                reverse_map[out_name] = f

    def replacer(match):
        path = match.group(1)
        parts = path.split(".")
        if len(parts) == 2:
            stage_name, field = parts
            if stage_name in result.get("_stages", {}):
                stage_results = result["_stages"][stage_name]
                if isinstance(stage_results, list) and stage_results:
                    val = stage_results[0].get(field, match.group(0))
                elif isinstance(stage_results, dict):
                    val = stage_results.get(field, match.group(0))
                else:
                    val = match.group(0)
            else:
                val = match.group(0)
        else:
            # Simple field: try original key first, then reverse-mapped English key
            val = result.get(path)
            if val is None and path in reverse_map:
                val = result.get(reverse_map[path])
            if val is None:
                val = match.group(0)
        if not isinstance(val, (str, int, float)):
            val = str(val)
        return str(val)
    return _re.sub(r"\{([^}]+)\}", replacer, template)

# 全局 reverse_map，由 scheduler_service.py 在 reverse_output_mapping 时注入
_global_output_mapping: dict = {}


def reverse_output_mapping(output_mapping: dict, results: list) -> list:
    """Reverse map output field names back to original field names."""
    if not output_mapping or not results:
        return results
    reverse_map = {}
    for out_name, mapping_info in output_mapping.items():
        if isinstance(mapping_info, dict):
            field = mapping_info.get("field", "")
            if field:
                reverse_map[out_name] = field
        else:
            reverse_map[out_name] = str(mapping_info)
    if not reverse_map:
        return results
    processed = []
    for record in results:
        if not isinstance(record, dict):
            processed.append(record)
            continue
        new_record = {}
        for k, v in record.items():
            new_k = reverse_map.get(k, k)
            new_record[new_k] = v
        processed.append(new_record)
    # Inject output_mapping into results so render_alert_template can use it
    if processed:
        for r in processed:
            if isinstance(r, dict):
                r["_output_mapping"] = output_mapping
    return processed

def _auto_detect_mapping(record: dict) -> dict:
    """Auto-detect field mapping from a record."""
    AUTO_FIELD_MAP = {
        "ip_address": ["src_ip", "source_ip", "client_ip", "ip", "attack_ip", "remote_addr"],
        "domain": ["server_name", "domain", "host", "hostname"],
        "attack_count": ["count", "total", "value", "attack_count"],
        "country": ["country", "geo_country"],
        "source": ["source", "rule_source", "log_source"],
        "duration": ["duration", "time_span"],
    }
    mapping = {}
    record_keys_lower = {k.lower(): k for k in record.keys()}
    for model_field, candidates in AUTO_FIELD_MAP.items():
        for candidate in candidates:
            if candidate in record:
                mapping[model_field] = candidate
                break
            if candidate.lower() in record_keys_lower:
                mapping[model_field] = record_keys_lower[candidate.lower()]
                break
    return mapping

class RuleExecutor:
    """规则动作执行器"""
    def __init__(self, db_session):
        self.db_session = db_session
        # 最近一次 process_actions 的分类计数
        self.last_mysql_written = 0
        self.last_alert_count = 0

    def process_actions(self, actions, es_results):
        written = 0
        self.last_mysql_written = 0
        self.last_alert_count = 0
        for action in actions:
            action_type = action.get("type", "")
            if action_type == "write_mysql":
                n = self._write_mysql(action, es_results)
                self.last_mysql_written += n
                written += n
            elif action_type == "create_alert":
                n = self._create_alert(action, es_results)
                self.last_alert_count += n
                written += n
        return written

    def _write_mysql(self, action, results):
        table = action.get("table", "")
        if not table:
            return 0
        mapping = action.get("mapping", {})
        if not mapping and results:
            for record in results:
                auto = _auto_detect_mapping(record)
                if auto:
                    mapping = auto
                    break
        written = 0

        # Collect all IPs and lookup country concurrently to avoid N x ~0.6s serial latency
        _all_ips = []
        _ip_seen = set()
        for record in results:
            _ip = self._resolve_field(mapping.get("ip_address", ""), record)
            if _ip and _ip not in _ip_seen:
                _ip_seen.add(_ip)
                _all_ips.append(_ip)
        _country_cache = {}
        if _all_ips:
            from concurrent.futures import ThreadPoolExecutor
            _mw = min(10, len(_all_ips))
            with ThreadPoolExecutor(max_workers=_mw) as _ex:
                _futs = {_ex.submit(_lookup_country_single, i): i for i in _all_ips}
                for _f in _futs:
                    try:
                        _country_cache[_futs[_f]] = _f.result()
                    except Exception:
                        _country_cache[_futs[_f]] = ""

        seen_ips = set()
        for record in results:
            ip = self._resolve_field(mapping.get("ip_address", ""), record)
            if not ip or ip in seen_ips:
                continue
            seen_ips.add(ip)
            # Extract time fields from ES aggregation result (epoch ms float from _time_stats)
            _raw_start = record.get("start_time")
            _raw_end = record.get("end_time")
            _raw_dur = record.get("duration")
            _start_dt = datetime.fromtimestamp(_raw_start / 1000) if _raw_start else None
            _end_dt = datetime.fromtimestamp(_raw_end / 1000) if _raw_end else None
            _dur_int = int(_raw_dur) if _raw_dur else (
                int(self._resolve_field(mapping.get("duration", "0"), record) or 0)
            )

            # Resolve domain: use mapping hint first; if empty, try original ES field names directly.
            # Note: reverse_output_mapping may rename server_name -> 攻击域名, so auto-detect
            # mapping {"domain": "server_name"} won't find the key after transformation.
            domain_val = self._resolve_field(mapping.get("domain", ""), record)
            if not domain_val:
                domain_val = record.get("server_name") or record.get("domain") or record.get("攻击域名") or ""
            # attack_count: auto-detect may not find it either; try direct keys too
            _cnt_raw = self._resolve_field(mapping.get("attack_count", ""), record)
            if not _cnt_raw:
                _cnt_raw = record.get("count") or record.get("doc_count") or record.get("攻击次数") or "1"
            count_val = int(_cnt_raw)

            country = self._resolve_field(mapping.get("country", ""), record)
            if not country and ip:
                country = _country_cache.get(ip, "")

            # Upsert: 存在则累加 attack_count + 更新时间，不存在则插入
            existing = self.db_session.query(Address).filter(
                Address.ip_address == ip,
                (Address.domain == domain_val) | (Address.domain.is_(None) & (domain_val == None))
            ).first()

            if existing:
                existing.attack_count = (existing.attack_count or 0) + count_val
                existing.end_time = _end_dt
                existing.duration = _dur_int
                existing.severity = mapping.get("severity", existing.severity or "medium")
                existing.updated_at = datetime.now()
            else:
                addr = Address(
                    ip_address=ip,
                    country=country,
                    domain=domain_val,
                    source=self._resolve_field(mapping.get("source", ""), record) or "es_rule",
                    attack_count=count_val,
                    start_time=_start_dt,
                    end_time=_end_dt,
                    duration=_dur_int,
                    severity=mapping.get("severity", "medium"),
                    status="active"
                )
                self.db_session.add(addr)
            written += 1
        self.db_session.commit()
        return written

    def _evaluate_severity(self, result: dict, default: str, conditions: list) -> str:
        """根据条件判断实际危险等级，默认中等，满足条件则升为指定等级"""
        # 等级优先级：critical > high > medium > low
        priority = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        effective = priority.get(default, 1)
        for cond in conditions:
            field = cond.get("field", "")
            op = cond.get("operator", "==")
            target = cond.get("value")
            up_severity = cond.get("severity", "high")
            actual_val = self._resolve_field(field, result)
            matched = self._compare(actual_val, op, target)
            if matched:
                up = priority.get(up_severity, 2)
                if up > effective:
                    effective = up
        # 转回等级名
        for name, p in priority.items():
            if p == effective:
                return name
        return default

    def _compare(self, actual, op, target):
        if actual is None:
            return False
        if op == "==":
            return str(actual) == str(target)
        if op == "!=":
            return str(actual) != str(target)
        if op == ">":
            try:
                return float(actual) > float(target)
            except (TypeError, ValueError):
                return False
        if op == ">=":
            try:
                return float(actual) >= float(target)
            except (TypeError, ValueError):
                return False
        if op == "<":
            try:
                return float(actual) < float(target)
            except (TypeError, ValueError):
                return False
        if op == "<=":
            try:
                return float(actual) <= float(target)
            except (TypeError, ValueError):
                return False
        if op == "contains":
            return str(target) in str(actual)
        return False

    def _create_alert(self, action, results):
        if not results:
            return 0
        rule_id = action.get("_rule_id")
        rule_name = action.get("_rule_name", "")
        rule_severity = action.get("severity", "medium")
        conditions = action.get("severity_conditions", [])
        db = self.db_session
        count = 0
        for result in results:
            ip = result.get("src_ip", result.get("ip_address", result.get("攻击地址", "")))
            domain = result.get("server_name", result.get("domain", result.get("攻击域名", "")))
            template = action.get("template", "")
            if template:
                content_text = render_alert_template(template, result)
            else:
                content_text = f"检测到 {ip} 攻击 {domain or '未知域名'}"
            title_template = action.get("title_template", "")
            if title_template:
                title = render_alert_template(title_template, result)
            elif rule_name:
                title = f"告警: {rule_name}"
            else:
                title = f"规则告警: {ip}"
            # 逐条评估危险等级
            final_severity = self._evaluate_severity(result, rule_severity, conditions)
            alert = Alert(
                rule_id=rule_id,
                rule_name=rule_name,
                title=title,
                content=content_text,
                event_count=result.get("count", 1),
                severity=final_severity,
                src_ip=ip,
                status="pending",
                raw_log=json.dumps(result, ensure_ascii=False, indent=2)
            )
            db.add(alert)
            count += 1
        db.commit()
        return count

    def _resolve_field(self, path, record):
        if not path:
            return None
        if path.isdigit():
            return path
        parts = path.split(".")
        val = record
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                return None
            if val is None:
                return None
        return str(val) if val is not None else None
