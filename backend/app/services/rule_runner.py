"""
规则执行 —— 手动执行和定时执行的**唯一**实现。

早先这里有两份完整拷贝：`scheduler_service.execute_scheduled_rule`（一个定义在
`add_rule_job` 内部的 90 行闭包）和 `api.rules.execute_rule_endpoint`（又 90 行）。
两份都在做「解析 stages → 查 ES → 反向映射 → 挂规则元数据 → 跑 actions → 存原始
日志 → 更新 last_run → 写执行日志」。手动和定时执行因此会逐渐走样，修一处漏一处。

调度器（独立进程）和 API（uvicorn）现在都只调 `run_rule()`。差别只在
``triggered_by`` 这个标记上 —— 它决定执行日志里怎么写，不决定业务怎么跑。

这个模块同时被两套解释器 import：web 用 venv 的 python，调度器用系统
python3.10。所以**不要**在这里引入 requirements 之外的依赖。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.utils.timezone import local_now


class ScheduleError(ValueError):
    """调度参数非法。

    转成 API 的 400、界面上的红字、调度器里的「这条规则不排期」。
    早先这个错误是 ``print`` 一下就 ``return`` —— 用户存了条错 cron，规则照常
    保存、永远不跑、界面上还看不出来。
    """


# ── 调度参数解析 / 预览 ────────────────────────────────────────────
_INTERVAL_UNITS = {
    "second": 1, "seconds": 1,
    "minute": 60, "minutes": 60,
    "hour": 3600, "hours": 3600,
    "day": 86400, "days": 86400,
}


def parse_schedule(schedule_type: str, schedule_value: str):
    """把规则表里的调度参数变成 APScheduler Trigger。不合法抛 ``ScheduleError``。

    ``schedule_type == "once"``（手动执行）返回 ``None`` —— 没有 trigger，语义上
    就是「不排期」，不是错误。
    """
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    stype = (schedule_type or "").strip()
    svalue = (schedule_value or "").strip()

    if stype == "once":
        return None

    if stype == "interval":
        parts = svalue.split()
        if len(parts) != 2:
            raise ScheduleError(
                f"执行周期应写成「数字 + 单位」，例如 5 minutes，现在是「{svalue or '（空）'}」"
            )
        try:
            value = int(parts[0])
        except ValueError:
            raise ScheduleError(f"执行周期的数字不合法：「{parts[0]}」") from None
        if value <= 0:
            raise ScheduleError("执行周期必须大于 0")

        unit = parts[1].lower()
        if unit not in _INTERVAL_UNITS:
            raise ScheduleError(
                f"不认识的时间单位「{parts[1]}」，可用：seconds / minutes / hours / days"
            )
        return IntervalTrigger(seconds=value * _INTERVAL_UNITS[unit])

    if stype == "cron":
        if not svalue:
            raise ScheduleError("Cron 表达式不能为空（分 时 日 月 周，如 0 9 * * *）")
        try:
            return CronTrigger.from_crontab(svalue)
        except Exception as exc:
            raise ScheduleError(f"Cron 表达式「{svalue}」不合法：{exc}") from exc

    raise ScheduleError(f"未知的执行方式「{stype}」，应为 once / interval / cron")


def next_runs(trigger, count: int = 3) -> List[datetime]:
    """从现在起的接下来几次触发时间。给界面上「下次执行: …」用。

    用游标推进而不是拿 ``previous_fire_time`` 往后推 —— 后者在 CronTrigger 上
    会原地打转（同一个 fire time 反复返回），实测过。
    """
    out: List[datetime] = []
    cursor = datetime.now().astimezone()
    for _ in range(count):
        nxt = trigger.get_next_fire_time(None, cursor)
        if nxt is None:
            break
        out.append(nxt)
        cursor = nxt + timedelta(microseconds=1)
    return out


def preview_schedule(schedule_type: str, schedule_value: str, count: int = 3) -> Dict[str, Any]:
    """调度参数预检。表单实时回显 + 保存前校验走的是同一条路。

    返回 ``{valid, error?, next_runs: [str], note?}``。**故意不抛异常** ——
    预览是个「边打字边问」的接口，打到一半的表达式本来就该回 ``valid: false``。
    """
    try:
        trigger = parse_schedule(schedule_type, schedule_value)
    except ScheduleError as exc:
        return {"valid": False, "error": str(exc), "next_runs": [], "schedule_type": schedule_type}

    if trigger is None:
        return {
            "valid": True,
            "error": None,
            "next_runs": [],
            "note": "手动执行，不排期",
            "schedule_type": schedule_type,
        }

    runs = next_runs(trigger, count)
    return {
        "valid": True,
        "error": None,
        "next_runs": [
            dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") for dt in runs
        ],
        "schedule_type": schedule_type,
        "schedule_value": (schedule_value or "").strip(),
    }


# ── 规则执行 ────────────────────────────────────────────────────────
@dataclass
class RuleRunResult:
    rule_id: int
    rule_name: str
    triggered_by: str            # scheduler / manual
    status: str = "success"      # success / error
    total: int = 0               # ES 查回来几条
    written: int = 0             # actions 写进去几条
    alert_count: int = 0         # 新建告警几条
    duration_ms: int = 0
    error: Optional[str] = None
    preview: List[Any] = field(default_factory=list)   # 只有手动执行才会带


def _get_es_config_from_db(db):
    from app.services.es_service import ESConfig
    from app.models.config import SystemConfig

    keys = ["es_host", "es_port", "es_scheme", "es_verify_certs",
            "es_user", "es_password", "es_index"]
    vals = {}
    for key in keys:
        row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        vals[key] = row.value if row else ""
    return ESConfig(
        host=vals.get("es_host", "localhost"),
        port=int(vals.get("es_port", "9200") or "9200"),
        scheme=vals.get("es_scheme", "https"),
        verify_certs=str(vals.get("es_verify_certs", "false")).lower() == "true",
        user=vals.get("es_user", ""),
        password=vals.get("es_password", ""),
        default_index=vals.get("es_index", "security-logs-*"),
    )


def store_raw_logs_for_alerts(db, es, stages, alert_ids) -> None:
    """给**本轮新建**的告警挂上 ES 原始日志。

    早先签名是 ``(db, es, stages, rule_id)``,内部按「最近 1 分钟 + 同 src_ip」
    猜哪些告警要挂 —— 一份 500 条的 ES JSON 会写进同 IP 的所有告警（包括几周前
    那条已 resolved 的），既错又爆库。调用方现在直接把本轮新建的 alert id 递进来。
    """
    from app.models.alert import Alert

    if not alert_ids:
        return
    try:
        if not stages:
            return
        stage1 = stages[0]
        index = stage1.get("index") or es.config.default_index
        filters = stage1.get("filters", [])
        time_window = stage1.get("time_window", {})

        alerts = db.query(Alert).filter(Alert.id.in_(list(alert_ids))).all()
        if not alerts:
            return

        for alert in alerts:
            ip = (alert.src_ip or "").strip()
            if not ip or alert.raw_logs:
                continue
            try:
                ip_filter = {"field": "src_ip", "operator": "equals", "value": ip}
                query_filters = (list(filters) if isinstance(filters, list) else []) + [ip_filter]
                raw_docs = es.execute_query(index, query_filters, time_window, limit=500)
                if raw_docs:
                    alert.raw_logs = json.dumps(raw_docs, ensure_ascii=False, default=str)
            except Exception as e:
                print(f"[RuleRunner] Failed to fetch raw logs for alert {alert.id} ({ip}): {e}")

        db.commit()
    except Exception as e:
        print(f"[RuleRunner] Failed to store raw logs: {e}")


def run_rule(
    db,
    rule_id: int,
    *,
    triggered_by: str = "manual",
    keep_preview: bool = False,
) -> RuleRunResult:
    """跑一次规则。ES 查询 + actions 写入 + 执行日志，全在这里。

    ``triggered_by`` 只影响执行日志里的标记（``scheduler`` / ``manual``），不影响
    业务逻辑 —— 定时跑和手动点「执行」必须跑出一样的东西。

    出错时返回 ``status="error"`` 而**不抛**：调用方（调度器线程 / HTTP handler）
    都希望拿到一个可记账的结果，而不是自己再包一层 try。``error`` 里是给用户看的
    摘要（截断到 2000 字符，和旧行为一致）。
    """
    from app.models.rule import Rule
    from app.services.es_service import ESService
    from app.services.rule_executor import (
        RuleExecutor,
        record_execution_log,
        reverse_output_mapping,
    )

    started = time.monotonic()
    result = RuleRunResult(rule_id=rule_id, rule_name="", triggered_by=triggered_by)

    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        result.status = "error"
        result.error = f"规则 {rule_id} 不存在"
        return result

    result.rule_name = rule.name or ""
    print(f"[RuleRunner] Executing rule: {result.rule_name} (ID: {rule_id}, by: {triggered_by})")

    try:
        es = ESService(config=_get_es_config_from_db(db))

        stages: List[Any] = []
        output_mapping: Dict[str, Any] = {}
        if rule.stages:
            try:
                stages = json.loads(rule.stages)
                output_mapping = json.loads(rule.output_mapping) if rule.output_mapping else {}
            except Exception:
                stages = []

        if stages:
            results = es.execute_multi_stage_rule(stages, output_mapping)
        else:
            nodes = json.loads(rule.nodes or "[]")
            results = es.execute_query(rule.es_index, nodes)

        # 反向映射 output_mapping 字段（中→英），确保 Action mapping 能匹配
        results = reverse_output_mapping(output_mapping, results)
        result.total = len(results)

        actions = json.loads(rule.actions or "[]")
        # 给每个动作带上规则元数据（create_alert / telegram 都要用）。
        # write_mysql 忽略这几个键也没副作用。
        for act in actions:
            act["_rule_id"] = rule.id
            act["_rule_name"] = rule.name
            act["_rule_severity"] = getattr(rule, "severity", "medium")

        executor = RuleExecutor(db)
        written = executor.process_actions(actions, results)
        result.written = written or 0
        result.alert_count = executor.last_alert_count or 0

        if executor.created_alert_ids and stages:
            store_raw_logs_for_alerts(db, es, stages, executor.created_alert_ids)

        rule.last_run = local_now()
        rule.run_count = (rule.run_count or 0) + 1
        db.commit()

        result.duration_ms = int((time.monotonic() - started) * 1000)
        if keep_preview:
            result.preview = list(results[:20])

        record_execution_log(
            db,
            rule_id=rule.id,
            rule_name=result.rule_name,
            alert_count=result.alert_count,
            detail={
                "trigger": triggered_by,
                "total_results": result.total,
                "mysql_written": executor.last_mysql_written,
                "alert_created": result.alert_count,
                "total_written": result.written,
            },
            status="success",
            duration_ms=result.duration_ms,
            triggered_by=triggered_by,
        )

        print(
            f"[RuleRunner] {result.rule_name} ok: {result.total} results, "
            f"{result.written} written, {result.duration_ms}ms"
        )

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        result.status = "error"
        result.error = str(e)[:2000]
        result.duration_ms = int((time.monotonic() - started) * 1000)
        print(f"[RuleRunner] {result.rule_name or rule_id} failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            record_execution_log(
                db,
                rule_id=rule_id,
                rule_name=result.rule_name,
                alert_count=0,
                detail={"trigger": triggered_by},
                status="error",
                error_message=result.error,
                duration_ms=result.duration_ms,
                triggered_by=triggered_by,
            )
        except Exception:
            pass

    return result


def record_missed_run(rule_id: int, rule_name: str = "", reason: str = "错过触发窗口", *, db=None) -> None:
    """把「漏跑」记进执行日志。

    APScheduler 的 ``misfire_grace_time`` 一过就把这一轮整个吞掉，什么痕迹都不留。
    ``max_instances=1`` 也一样 —— 并发触发直接丢弃。这两件事以前在界面上完全看
    不见，于是「调度器绿着灯但一条规则都没跑」能一直糊弄下去。

    ``db`` 可注入 —— 调度器线程不传，自己开 SessionLocal；测试传进来的
    in-memory session。**别在这里默认开 SessionLocal**：那会写到另一个库去。
    """
    from app.services.rule_executor import record_execution_log

    def _write(session):
        record_execution_log(
            session,
            rule_id=rule_id,
            rule_name=rule_name or "",
            alert_count=0,
            detail={"trigger": "scheduler", "reason": reason},
            status="missed",
            error_message=reason,
            duration_ms=0,
            triggered_by="scheduler",
        )

    if db is not None:
        _write(db)
        return

    from app.models.base import SessionLocal
    own = SessionLocal()
    try:
        _write(own)
    finally:
        own.close()
