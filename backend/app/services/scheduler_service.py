"""
规则调度器服务 (v2)
从原版 Flask 迁移：去除 Flask app context，改用 SQLAlchemy session + v2 es_service
"""
import json
from datetime import datetime, timedelta

from app.utils.timezone import local_now

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.models.base import SessionLocal
from app.models.rule import Rule
from app.models.alert import Alert
from app.models.config import SystemConfig
from app.services.es_service import ESService, ESConfig
from app.services.rule_executor import RuleExecutor


def _get_es_config_from_db(db) -> ESConfig:
    """从 SystemConfig 表读取 ES 配置（与 rules.py 的 _get_es_config 一致）"""
    cfg_keys = ["es_host", "es_port", "es_scheme", "es_verify_certs", "es_user", "es_password", "es_index"]
    cfg_values = {}
    for key in cfg_keys:
        cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        cfg_values[key] = cfg.value if cfg else ""
    return ESConfig(
        host=cfg_values.get("es_host", "localhost"),
        port=int(cfg_values.get("es_port", "9200") or "9200"),
        scheme=cfg_values.get("es_scheme", "https"),
        verify_certs=str(cfg_values.get("es_verify_certs", "false")).lower() == "true",
        user=cfg_values.get("es_user", ""),
        password=cfg_values.get("es_password", ""),
        default_index=cfg_values.get("es_index", "security-logs-*")
    )


def _store_raw_logs_for_alerts(db, es, stages, alert_ids):
    """给**指定**告警挂上 ES 原始日志。

    早先签名是 ``(db, es, stages, rule_id)``，内部按「最近 1 分钟 + 同 src_ip」
    猜哪些告警要挂 —— 一份 500 条的 ES JSON 会写进同 IP 的所有告警（包括几周前
    那条已 resolved 的），既错又爆库。调用方现在直接把本轮新建的 alert id 递进来。
    """
    from app.models.alert import Alert
    from datetime import timedelta

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

        # 每个 IP 查一次，结果只挂到**这个 IP 名下、本轮新建的**告警上
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
                print(f"[Scheduler] Failed to fetch raw logs for alert {alert.id} ({ip}): {e}")

        db.commit()
    except Exception as e:
        print(f"[Scheduler] Failed to store raw logs: {e}")


class SchedulerService:
    """调度器服务单例"""

    _instance = None
    _scheduler = None
    # job_id -> (schedule_type, schedule_value)，用来判断「调度参数变没变」。
    # 对账时不能无脑重加 job：IntervalTrigger 一被 replace 就把起算点重置，
    # 每分钟 reconcile 一次的话定时规则永远不会触发。
    _job_specs: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._scheduler = BackgroundScheduler()
        return cls._instance

    @property
    def scheduler(self):
        return self._scheduler

    def start(self):
        """启动调度器"""
        if not self._scheduler.running:
            self._scheduler.start()
            self.write_heartbeat()
            self._add_retention_job()
            print(f"[Scheduler] Started at {local_now()}")

    def _add_retention_job(self):
        """每天 03:17 清一次旧日志。

        刻意避开整点 —— 整点是备份/巡检脚本的默认档期，抢同一个 MySQL 连接池
        会互相拖慢。replace_existing + 独立 job_id，reconcile 不会碰它。
        """
        def _run_retention():
            try:
                from app.services.retention import run_retention
                deleted = run_retention()
                if deleted:
                    print(f"[Scheduler] Retention pruned: {deleted}")
            except Exception as exc:
                print(f"[Scheduler] Retention failed: {exc}")

        try:
            self._scheduler.add_job(
                _run_retention,
                trigger=CronTrigger(hour=3, minute=17),
                id="retention_daily",
                name="每日数据保留清理",
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
        except Exception as exc:
            print(f"[Scheduler] Failed to register retention job: {exc}")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown()
            print(f"[Scheduler] Stopped at {local_now()}")

    @staticmethod
    def write_heartbeat() -> None:
        """Stamp ``scheduler_heartbeat`` in SystemConfig.

        ``/api/scheduler/status`` reads this instead of shelling out to
        ``pgrep`` (which leaked process info to callers and N+1'd the DB).
        A heartbeat older than 5 minutes means the scheduler is down.
        """
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == "scheduler_heartbeat").first()
            stamp = local_now().isoformat(timespec="seconds")
            if row is None:
                row = SystemConfig(key="scheduler_heartbeat", value=stamp)
                db.add(row)
            else:
                row.value = stamp
                row.updated_at = local_now()
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[Scheduler] Failed to write heartbeat: {exc}")
        finally:
            db.close()

    def add_rule_job(self, rule):
        """添加规则调度任务"""
        if not rule.is_enabled:
            return

        job_id = f'rule_{rule.id}'

        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        if rule.schedule_type == 'once':
            # 手动执行，不需要调度
            return

        try:
            if rule.schedule_type == 'interval':
                # 解析 interval 格式: "3 minutes", "2 hours", "1 days"
                parts = (rule.schedule_value or '').split()
                if len(parts) == 2:
                    value = int(parts[0])
                    unit = parts[1].lower()

                    if unit in ['second', 'seconds']:
                        seconds = value
                    elif unit in ['minute', 'minutes']:
                        seconds = value * 60
                    elif unit in ['hour', 'hours']:
                        seconds = value * 3600
                    elif unit in ['day', 'days']:
                        seconds = value * 86400
                    else:
                        print(f"[Scheduler] Unknown interval unit: {unit}")
                        return

                    trigger = IntervalTrigger(seconds=seconds)
                else:
                    print(f"[Scheduler] Invalid interval value: {rule.schedule_value}")
                    return

            elif rule.schedule_type == 'cron':
                trigger = CronTrigger.from_crontab(rule.schedule_value)

            else:
                print(f"[Scheduler] Unknown schedule type: {rule.schedule_type}")
                return

            def execute_scheduled_rule():
                """执行定时规则（后台线程，独立 session）"""
                db = SessionLocal()
                try:
                    rule_obj = db.query(Rule).filter(Rule.id == rule.id).first()
                    if not rule_obj or not rule_obj.is_enabled:
                        return

                    print(f"[Scheduler] Executing rule: {rule_obj.name} (ID: {rule.id})")

                    es = ESService(config=_get_es_config_from_db(db))

                    stages = []
                    output_mapping = {}
                    if rule_obj.stages:
                        try:
                            stages = json.loads(rule_obj.stages)
                            output_mapping = json.loads(rule_obj.output_mapping) if rule_obj.output_mapping else {}
                        except Exception:
                            pass

                    if stages:
                        results = es.execute_multi_stage_rule(stages, output_mapping)
                    else:
                        nodes = json.loads(rule_obj.nodes or '[]')
                        results = es.execute_query(rule_obj.es_index, nodes)

                    # 反向映射 output_mapping 字段（中→英），确保 Action mapping 能匹配
                    from app.services.rule_executor import reverse_output_mapping, record_execution_log
                    results = reverse_output_mapping(output_mapping, results)

                    # 写入 MySQL（actions）
                    actions = json.loads(rule_obj.actions or '[]')
                    # 给每个动作带上规则元数据（create_alert / telegram 都要用）
                    for act in actions:
                        act["_rule_id"] = rule_obj.id
                        act["_rule_name"] = rule_obj.name
                        act["_rule_severity"] = getattr(rule_obj, "severity", "medium")
                    executor = RuleExecutor(db)
                    written = executor.process_actions(actions, results)

                    # 存储触发告警的ES原始日志
                    if executor.created_alert_ids and stages:
                        _store_raw_logs_for_alerts(db, es, stages, executor.created_alert_ids)

                    # 更新规则状态
                    rule_obj.last_run = local_now()
                    rule_obj.run_count = (rule_obj.run_count or 0) + 1
                    db.commit()

                    # 记录执行日志
                    record_execution_log(
                        db,
                        rule_id=rule_obj.id,
                        rule_name=rule_obj.name,
                        alert_count=executor.last_alert_count,
                        detail={
                            "trigger": "scheduler",
                            "total_results": len(results),
                            "mysql_written": executor.last_mysql_written,
                            "alert_created": executor.last_alert_count,
                            "total_written": written
                        },
                        status="success"
                    )

                    print(f"[Scheduler] Rule {rule_obj.name} executed: {len(results)} results, {written} written")

                except Exception as e:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    print(f"[Scheduler] Rule execution failed: {e}")
                    import traceback
                    traceback.print_exc()
                    # 记录失败执行日志
                    try:
                        from app.services.rule_executor import record_execution_log
                        record_execution_log(
                            db,
                            rule_id=rule.id,
                            rule_name=getattr(rule, 'name', ''),
                            alert_count=0,
                            detail={"trigger": "scheduler"},
                            status="error",
                            error_message=str(e)[:2000]
                        )
                    except Exception:
                        pass
                finally:
                    db.close()

            self._scheduler.add_job(
                execute_scheduled_rule,
                trigger=trigger,
                id=job_id,
                name=rule.name,
                replace_existing=True,
                # 进程重启/短暂卡顿不该把这一轮整个吞掉，也不该并发跑同一个规则
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )
            self._job_specs[job_id] = (
                rule.schedule_type,
                (rule.schedule_value or "").strip(),
            )

            # 更新 next_run（APScheduler 3.x 兼容）
            try:
                job = self._scheduler.get_job(job_id)
                if job is not None:
                    db2 = SessionLocal()
                    try:
                        r2 = db2.query(Rule).filter(Rule.id == rule.id).first()
                        if r2:
                            nrt = getattr(job, 'next_run_time', None)
                            r2.next_run = nrt
                            db2.commit()
                    finally:
                        db2.close()
            except Exception as e:
                print(f"[Scheduler] Failed to update next_run for rule {rule.id}: {e}")

            print(f"[Scheduler] Added job for rule: {rule.name} (ID: {rule.id}, Type: {rule.schedule_type}, Value: {rule.schedule_value})")

        except Exception as e:
            print(f"[Scheduler] Failed to add job for rule {rule.id}: {e}")
            import traceback
            traceback.print_exc()

    def remove_rule_job(self, rule_id):
        """移除规则调度任务"""
        job_id = f'rule_{rule_id}'
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            print(f"[Scheduler] Removed job for rule ID: {rule_id}")
        self._job_specs.pop(job_id, None)

    def reconcile(self) -> None:
        """让内存里的 job 集合跟规则表对齐。

        API（uvicorn）和调度器（run_scheduler.py）是两个进程，JobStore 又是内存型，
        所以 rules.py 里那些 ``# TODO: Add to scheduler`` 在架构上根本够不着 ——
        新建的定时规则在重启调度器前一次都不会跑，改了周期仍按旧周期跑。

        不引 IPC，改成定时对账：一个 tick 内收敛，进程崩了也能自愈。
        """
        db = SessionLocal()
        try:
            desired = {
                r.id: r
                for r in db.query(Rule).filter(
                    Rule.is_enabled.is_(True),
                    Rule.schedule_type.in_(['interval', 'cron'])
                ).all()
            }
        finally:
            db.close()

        # 1) 清掉已经不该跑的：规则被删、被停用、或改成了「手动执行」
        for job in list(self._scheduler.get_jobs()):
            if not str(job.id).startswith("rule_"):
                continue
            try:
                rid = int(str(job.id).split("_", 1)[1])
            except (ValueError, IndexError):
                continue
            if rid not in desired:
                self.remove_rule_job(rid)

        # 2) 只在调度参数真变了的时候重建；没变就别碰，否则定时器时钟被清零
        for rid, rule in desired.items():
            job_id = f'rule_{rid}'
            spec = (rule.schedule_type, (rule.schedule_value or '').strip())
            if self._scheduler.get_job(job_id) is not None and self._job_specs.get(job_id) == spec:
                continue
            self.add_rule_job(rule)

    def load_all_rules(self):
        """加载所有启用的定时规则"""
        self.reconcile()
        print(f"[Scheduler] Loaded {len(self._job_specs)} scheduled rules")

    def get_jobs_info(self):
        """获取所有任务信息"""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': str(job.next_run_time) if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs


# 全局单例
scheduler_service = SchedulerService()
