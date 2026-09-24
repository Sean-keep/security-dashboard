"""
规则调度器服务

架构：uvicorn（web）和 run_scheduler.py（调度器）是两个进程，APScheduler 的
JobStore 又是内存型，所以两边够不着对方的 job。**不引 IPC**，改成定时对账 ——
一个 tick 内收敛，进程崩了也能自愈。

        rules.py 改规则  →  置 scheduler_dirty = 1（SystemConfig）
        run_scheduler.py →  每 5 秒看一眼脏位，有就 reconcile
                         →  每 60 秒兜底全量对账一次 + 写进程心跳

对账时**不能**无脑重加 job：IntervalTrigger 一被 replace 就把起算点重置，每分钟
reconcile 一次的话定时规则永远不会触发。所以 `_job_specs` 记着「调度参数指纹」，
没变就不碰。

业务逻辑不在这里 —— 跑规则统一走 `app.services.rule_runner.run_rule`。
"""
import json

from app.utils.timezone import local_now

from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobEvent,
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.models.base import SessionLocal
from app.models.rule import Rule
from app.models.config import SystemConfig
from app.services import rule_runner


# 运行态键。不是配置，GET /settings/config 会把 runtime 分组过滤掉。
HEARTBEAT_KEY = "scheduler_heartbeat"       # 进程主循环还活着
LAST_ACTIVITY_KEY = "scheduler_last_activity"  # 最近一次真正跑完的任务
DIRTY_KEY = "scheduler_dirty"               # 规则表被改过，调度器该对账了

# 心跳超过这个秒数就认为调度器停了。60 秒一轮写一次，留一倍余量。
HEARTBEAT_STALE_SECONDS = 300


class SchedulerService:
    """调度器服务单例（单进程使用；模块底部有全局实例）。"""

    def __init__(self):
        self._scheduler = BackgroundScheduler()
        # job_id -> (schedule_type, schedule_value)，用来判断「调度参数变没变」
        self._job_specs: dict = {}
        self._listen_events()

    @property
    def scheduler(self):
        return self._scheduler

    # ── 生命周期 ──────────────────────────────────────────────────
    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            self.write_heartbeat()
            self._add_retention_job()
            print(f"[Scheduler] Started at {local_now()}")

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            print(f"[Scheduler] Stopped at {local_now()}")

    # ── 心跳 / 脏标记 ────────────────────────────────────────────
    @staticmethod
    def _stamp(key: str) -> None:
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
            stamp = local_now().isoformat(timespec="seconds")
            if row is None:
                # group_name=runtime —— 别出现在系统设置页上
                db.add(SystemConfig(key=key, value=stamp, label=key,
                                    description="调度器运行态", group_name="runtime"))
            else:
                row.value = stamp
                row.updated_at = local_now()
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[Scheduler] Failed to stamp {key}: {exc}")
        finally:
            db.close()

    @classmethod
    def write_heartbeat(cls) -> None:
        """进程级心跳：主循环还在转。**不代表任务在跑** —— 线程池卡死也照写不误，
        所以还要有 `write_activity()` 那条「最近一次真正跑完」。"""
        cls._stamp(HEARTBEAT_KEY)

    @classmethod
    def write_activity(cls) -> None:
        """任务级心跳：最近一次真正跑完（成功或失败都算）的任务。"""
        cls._stamp(LAST_ACTIVITY_KEY)

    @staticmethod
    def mark_dirty() -> None:
        """规则表被改动了。web 进程调这个，调度器下一个 tick（≤5 秒）就对账。

        没有 IPC 也能把「新建规则要等最多一分钟才生效」压到秒级。
        """
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == DIRTY_KEY).first()
            if row is None:
                db.add(SystemConfig(key=DIRTY_KEY, value="1", label=DIRTY_KEY,
                                    description="调度器运行态", group_name="runtime"))
            else:
                row.value = "1"
                row.updated_at = local_now()
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[Scheduler] Failed to mark dirty: {exc}")
        finally:
            db.close()

    @staticmethod
    def consume_dirty() -> bool:
        """读并清掉脏位。返回「刚才有没有人改过规则表」。"""
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == DIRTY_KEY).first()
            if row is None or (row.value or "") != "1":
                return False
            row.value = "0"
            row.updated_at = local_now()
            db.commit()
            return True
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[Scheduler] Failed to consume dirty flag: {exc}")
            return False
        finally:
            db.close()

    # ── 漏跑监听 ─────────────────────────────────────────────────
    def _listen_events(self) -> None:
        """APScheduler 的漏跑/丢弃事件落到执行日志里。

        `misfire_grace_time` 一过这一轮被整个吞掉、`max_instances=1` 把并发触发
        直接丢弃 —— 这两件事以前一点痕迹都不留，于是「灯是绿的但一条没跑」能一直
        糊弄下去。落了 `status='missed'` 之后界面上就露馅了。
        """

        def _on_missed(event: JobEvent) -> None:
            self._record_skip(event, reason=f"错过触发窗口（misfire_grace_time） job_id={event.job_id}")

        def _on_max_instances(event: JobEvent) -> None:
            self._record_skip(event, reason=f"上一轮还没跑完，本轮被丢弃（max_instances=1） job_id={event.job_id}")

        self._scheduler.add_listener(_on_missed, EVENT_JOB_MISSED)
        self._scheduler.add_listener(_on_max_instances, EVENT_JOB_MAX_INSTANCES)

    @staticmethod
    def _record_skip(event: JobEvent, *, reason: str) -> None:
        job_id = str(getattr(event, "job_id", "") or "")
        if not job_id.startswith("rule_"):
            return
        try:
            rid = int(job_id.split("_", 1)[1])
        except (ValueError, IndexError):
            return
        name = ""
        try:
            db = SessionLocal()
            try:
                rule = db.query(Rule).filter(Rule.id == rid).first()
                name = rule.name if rule else ""
            finally:
                db.close()
        except Exception:
            pass
        print(f"[Scheduler] MISSED rule_{rid} ({name}): {reason}")
        rule_runner.record_missed_run(rid, rule_name=name, reason=reason)

    # ── 内置任务 ─────────────────────────────────────────────────
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
                SchedulerService.write_activity()
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

    # ── 规则 job ─────────────────────────────────────────────────
    def add_rule_job(self, rule):
        """把一条规则挂上调度器。调度参数非法就**不挂**，并如实说出口。"""
        if not rule.is_enabled:
            return

        job_id = f"rule_{rule.id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        if rule.schedule_type == "once":
            # 手动执行，不需要调度
            self._job_specs.pop(job_id, None)
            return

        try:
            trigger = rule_runner.parse_schedule(rule.schedule_type, rule.schedule_value)
        except rule_runner.ScheduleError as exc:
            # 早先这里是 print 一下就 return —— 规则照常保存、永远不跑、界面上
            # 还看不出来。现在至少日志里说清楚，且 status 接口会把它标红。
            print(f"[Scheduler] Rule {rule.id} 「{rule.name}」不排期：{exc}")
            self._job_specs.pop(job_id, None)
            return

        rule_id = rule.id

        def execute_scheduled_rule(rule_id=rule_id):
            """调度器线程里的入口：开独立 session，跑完记账并打活动心跳。"""
            db = SessionLocal()
            try:
                rule_obj = db.query(Rule).filter(Rule.id == rule_id).first()
                if not rule_obj or not rule_obj.is_enabled:
                    return
                rule_runner.run_rule(db, rule_id, triggered_by="scheduler")
            finally:
                db.close()
                SchedulerService.write_activity()

        try:
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
            self._touch_next_run(rule_id, job_id)
            print(
                f"[Scheduler] Added job for rule: {rule.name} "
                f"(ID: {rule.id}, Type: {rule.schedule_type}, Value: {rule.schedule_value})"
            )
        except Exception as e:
            print(f"[Scheduler] Failed to add job for rule {rule.id}: {e}")
            import traceback
            traceback.print_exc()

    def _touch_next_run(self, rule_id: int, job_id: str) -> None:
        """把 APScheduler 算出来的 next_run_time 写回规则表，界面上才看得见下次几点跑。"""
        job = self._scheduler.get_job(job_id)
        db = SessionLocal()
        try:
            rule = db.query(Rule).filter(Rule.id == rule_id).first()
            if rule is not None:
                rule.next_run = getattr(job, "next_run_time", None) if job else None
                db.commit()
        except Exception as e:
            print(f"[Scheduler] Failed to update next_run for rule {rule_id}: {e}")
        finally:
            db.close()

    def remove_rule_job(self, rule_id):
        job_id = f"rule_{rule_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            print(f"[Scheduler] Removed job for rule ID: {rule_id}")
        self._job_specs.pop(job_id, None)

    def reconcile(self) -> None:
        """让内存里的 job 集合跟规则表对齐。

        新建/改周期/停用/删除都靠这里收敛 —— web 进程改完只 `mark_dirty()`。
        """
        db = SessionLocal()
        try:
            desired = {
                r.id: r
                for r in db.query(Rule).filter(
                    Rule.is_enabled.is_(True),
                    Rule.schedule_type.in_(["interval", "cron"]),
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
            job_id = f"rule_{rid}"
            spec = (rule.schedule_type, (rule.schedule_value or "").strip())
            if self._scheduler.get_job(job_id) is not None and self._job_specs.get(job_id) == spec:
                continue
            self.add_rule_job(rule)

    def load_all_rules(self):
        self.reconcile()
        print(f"[Scheduler] Loaded {len(self._job_specs)} scheduled rules")


# 全局实例
scheduler_service = SchedulerService()
