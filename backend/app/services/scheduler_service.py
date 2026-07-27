"""
规则调度器服务 (v2)
从原版 Flask 迁移：去除 Flask app context，改用 SQLAlchemy session + v2 es_service
"""
import json
from datetime import datetime

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


class SchedulerService:
    """调度器服务单例"""

    _instance = None
    _scheduler = None

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
            print(f"[Scheduler] Started at {datetime.now()}")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown()
            print(f"[Scheduler] Stopped at {datetime.now()}")

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
                    for act in actions:
                        if act.get("type") == "create_alert":
                            act["_rule_id"] = rule_obj.id
                            act["_rule_name"] = rule_obj.name
                            act["_rule_severity"] = getattr(rule_obj, "severity", "medium")
                    executor = RuleExecutor(db)
                    written = executor.process_actions(actions, results)

                    # 更新规则状态
                    rule_obj.last_run = datetime.now()
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
                replace_existing=True
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

    def load_all_rules(self):
        """加载所有启用的定时规则"""
        db = SessionLocal()
        try:
            rules = db.query(Rule).filter(
                Rule.is_enabled == True,
                Rule.schedule_type.in_(['interval', 'cron'])
            ).all()

            for rule in rules:
                self.add_rule_job(rule)

            print(f"[Scheduler] Loaded {len(rules)} scheduled rules")
        finally:
            db.close()

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
