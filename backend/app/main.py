"""
Security Dashboard Backend - FastAPI Application
"""
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.base import init_db, get_db
from app.api import auth, addresses, rules, alerts, settings as settings_api
from app.api.dashboard import router as dashboard_router
from app.api.security import get_current_user
from app.api.inspect import router as inspect_router
from app.api.reports import router as reports_router
from app.api.remote import router as remote_router
from app.api.execution_logs import router as execution_logs_router
from app.api.logs import router as logs_router
from app.api.raw_logs import router as raw_logs_router
from app.utils.timezone import format_dt, local_now


def _migrate_login_logs() -> None:
    """One-off: copy historical login_logs into the operation-log centre."""
    try:
        from app.models.base import SessionLocal as _SL
        from app.models.user import LoginLog as _LoginLog
        from app.models.operation_log import OperationLog as _OperationLog

        _mig_db = _SL()
        try:
            if _mig_db.query(_OperationLog).filter(_OperationLog.log_type == "login").first():
                return
            _old_logs = _mig_db.query(_LoginLog).order_by(_LoginLog.created_at.asc()).all()
            for _ll in _old_logs:
                _mig_db.add(_OperationLog(
                    log_type="login",
                    username=_ll.username or "",
                    action="登录",
                    ip_address=_ll.ip_address,
                    status="success" if _ll.status == "success" else "failure",
                    detail=_ll.reason or "",
                    created_at=_ll.created_at,
                ))
            _mig_db.commit()
            if _old_logs:
                print(f"✅ 已迁移 {len(_old_logs)} 条历史登录日志到日志中心")
        finally:
            _mig_db.close()
    except Exception as _e:
        print(f"⚠️ 登录日志迁移失败: {_e}")


def _migrate_legacy_roles() -> None:
    """旧角色名 → 三权分立角色名。

    唯一需要改写的存量是 ``admin``：它以前一个人握着账号+授权+审计，正是三权
    分立要拆开的那把「全能钥匙」。迁到 ``sys_admin``（账号+系统配置+业务），
    授权和审计需要另外建号 —— 安全管理员 / 审计管理员。

    ``operator`` / ``viewer`` 语义没变，不动。
    """
    try:
        from app.models.base import SessionLocal
        from app.models.user import User

        _db = SessionLocal()
        try:
            rows = _db.query(User).filter(User.role == "admin").all()
            for u in rows:
                u.role = "sys_admin"
            if rows:
                _db.commit()
                print(f"✅ 旧角色迁移完成：{len(rows)} 个 admin → sys_admin")
        finally:
            _db.close()
    except Exception as _e:
        print(f"⚠️ 旧角色迁移失败: {_e}")


def _seed_role_permissions() -> None:
    """把内置默认矩阵补进 role_permissions 表（只补缺失，不覆盖已有勾选）。

    不挂在 SEED_SYSTEM_CONFIG 上：矩阵是 RBAC 的落库形态，跟 users 表一个级别，
    不是可选的种子数据。系统管理员之后在界面上改，改的是表里的行。
    """
    try:
        from app.models.base import SessionLocal
        from app.core.permissions import ensure_role_permissions

        _rp_db = SessionLocal()
        try:
            ensure_role_permissions(_rp_db)
            print("✅ 角色权限矩阵初始化完成")
        finally:
            _rp_db.close()
    except Exception as _e:
        print(f"⚠️ 初始化角色权限矩阵失败: {_e}")


def _seed_system_config() -> None:
    """Seed system-config defaults (idempotent)."""
    if not settings.SEED_SYSTEM_CONFIG:
        return
    try:
        from app.models.base import SessionLocal
        from app.models.config import SystemConfig

        _cfg_db = SessionLocal()
        try:
            _defaults = [
                ("prometheus_url", "http://localhost:9090", "Prometheus 地址", "Prometheus 服务地址", "prometheus"),
                ("prometheus_user", "", "Prometheus 用户名", "Basic Auth 用户名（可选）", "prometheus"),
                ("prometheus_password", "", "Prometheus 密码", "Basic Auth 密码（可选）", "prometheus"),
                ("es_host", "", "ES 地址", "Elasticsearch 主机地址", "es"),
                ("es_port", "9200", "ES 端口", "Elasticsearch 端口", "es"),
                ("es_scheme", "https", "ES 协议", "http 或 https", "es"),
                ("es_verify_certs", "false", "ES 验证证书", "https 时是否验证证书 (true/false)", "es"),
                ("es_user", "", "ES 用户名", "Elasticsearch 用户名（可选）", "es"),
                ("es_password", "", "ES 密码", "Elasticsearch 密码（可选）", "es"),
                ("es_index", "security-logs-*", "ES 索引", "查询使用的索引通配符", "es"),
                ("mysql_host", "localhost", "MySQL 地址", "MySQL 主机地址", "mysql"),
                ("mysql_port", "3306", "MySQL 端口", "MySQL 端口", "mysql"),
                ("mysql_user", "root", "MySQL 用户", "MySQL 用户名", "mysql"),
                ("mysql_password", "", "MySQL 密码", "MySQL 密码", "mysql"),
                ("mysql_database", "security_dashboard", "MySQL 数据库", "数据库名", "mysql"),
                ("grafana_url", "", "Grafana 地址", "Grafana URL，如 http://192.168.1.100:3000", "grafana"),
                ("grafana_auth_mode", "apikey", "Grafana 认证方式", "apikey 或 basic", "grafana"),
                ("grafana_api_key", "", "Grafana API Key", "API Key（可选）", "grafana"),
                ("grafana_user", "", "Grafana 用户名", "Basic Auth 用户名（可选）", "grafana"),
                ("grafana_password", "", "Grafana 密码", "Basic Auth 密码（可选）", "grafana"),
                # 安全策略。早先这几项只在 settings 里兜底、从不进 SystemConfig，
                # 于是 PUT /settings/config 会静默丢弃它们 —— 管理员改了却没生效。
                ("login_max_attempts", "5", "登录失败锁定阈值",
                 "连续失败多少次后锁定账号（需重启生效）", "security"),
                ("login_lockout_minutes", "15", "登录锁定时长（分钟）",
                 "锁定多少分钟后自动解锁（需重启生效）", "security"),
                ("virustotal_api_key", "", "VirusTotal API Key",
                 "可选；配置后告警详情可查 IP 信誉", "security"),
                # 数据保留（天）。0 = 不清理。每日 03:17 由调度器执行。
                ("retention_ingest_logs_days", "30", "推送数据保留（天）",
                 "ingest_logs 超过该天数自动删除；0 = 不清理", "retention"),
                ("retention_execution_logs_days", "30", "规则执行记录保留（天）",
                 "0 = 不清理", "retention"),
                ("retention_operation_logs_days", "90", "操作日志保留（天）",
                 "0 = 不清理", "retention"),
                ("retention_login_logs_days", "90", "登录日志保留（天）",
                 "0 = 不清理", "retention"),
                ("retention_remote_executions_days", "30", "远程执行结果保留（天）",
                 "0 = 不清理", "retention"),
                ("retention_alerts_resolved_days", "180", "已结束告警保留（天）",
                 "只清 resolved / false_positive；pending/confirmed 不动。0 = 不清理", "retention"),
                # ── 界面外观（UI 管理）。全站一套，不是个人偏好。──
                ("ui_theme", "light", "主题模式", "light 或 dark", "ui"),
                ("ui_primary_color", "#409eff", "主色", "Element Plus 主色（十六进制）", "ui"),
                ("ui_density", "default", "表格密度", "default / small / large", "ui"),
                ("ui_sidebar_collapse", "false", "侧边栏默认折叠", "true 或 false", "ui"),
                ("ui_site_title", "安全巡检平台", "站点标题", "侧边栏左上角显示的名称", "ui"),
                # /metrics 的可选令牌。留空 = 内网开放抓取；非空则要求 ?token=。
                ("metrics_token", "", "Metrics 令牌",
                 "非空时 /metrics?token= 必须匹配；留空则开放抓取", "security"),
            ]
            for _key, _val, _label, _desc, _grp in _defaults:
                if not _cfg_db.query(SystemConfig).filter(SystemConfig.key == _key).first():
                    _cfg_db.add(SystemConfig(
                        key=_key, value=_val, label=_label,
                        description=_desc, group_name=_grp,
                    ))
            _cfg_db.commit()
            print("✅ 系统配置初始化完成")
        finally:
            _cfg_db.close()
    except Exception as _e:
        print(f"⚠️ 初始化系统配置失败: {_e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    print(f"📦 Database: {'SQLite' if settings.USE_SQLITE else 'MySQL'}")
    print(f"🔍 ES: {settings.ES_HOST}:{settings.ES_PORT}")

    init_db()
    _migrate_login_logs()
    _migrate_legacy_roles()
    _seed_role_permissions()
    _seed_system_config()

    # 调度器由独立进程运行（run_scheduler.py），不在 web worker 中启动
    print("ℹ️ 调度器由独立进程运行")

    yield

    print("👋 Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS: explicit origin list + credentials. Never `*` with credentials —
# that combination is either rejected by browsers or a credential leak.
_origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else [],
    allow_credentials=bool(_origins),
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Refresh-Token", "X-Ingest-Token"],
    max_age=600,
)

app.include_router(auth.router, prefix="/api")
app.include_router(addresses.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(execution_logs_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(reports_router)
app.include_router(inspect_router)
app.include_router(remote_router, prefix="/api")
app.include_router(raw_logs_router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
def health(db=Depends(get_db)):
    """Liveness/readiness: verifies the DB is reachable, not just that the
    process is up. Used by compose healthchecks."""
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        # /health 无需鉴权。把异常原文吐出去等于给外人一份连接串/驱动栈。
        # 只报「挂了」，细节进日志。
        import logging
        logging.getLogger("app.health").exception("database liveness probe failed")
        return {"status": "degraded", "database": "error"}
    return {"status": "healthy", "database": "ok" if db_ok else "unknown"}


def _stamp_age_seconds(value: str):
    """ISO 时间戳距今多少秒。解析失败 / 空 → None。"""
    if not value:
        return None
    try:
        from datetime import datetime
        ts = datetime.fromisoformat(value)
        return max(0, int((local_now() - ts).total_seconds()))
    except (ValueError, TypeError):
        return None


def _scheduler_snapshot(db) -> dict:
    """调度器状态一次算完：心跳、任务、最近执行、毛病清单。

    状态接口和健康接口共用这一份 —— 以前两个接口各查一遍，口径会漂。
    """
    from app.models.config import SystemConfig
    from app.models.rule import Rule
    from app.models.execution_log import RuleExecutionLog
    from app.services.scheduler_service import HEARTBEAT_STALE_SECONDS
    from sqlalchemy import func

    stamps = {
        r.key: (r.value or "")
        for r in db.query(SystemConfig)
        .filter(SystemConfig.key.in_(["scheduler_heartbeat", "scheduler_last_activity"]))
        .all()
    }
    heartbeat_at = stamps.get("scheduler_heartbeat") or ""
    activity_at = stamps.get("scheduler_last_activity") or ""
    hb_age = _stamp_age_seconds(heartbeat_at)
    act_age = _stamp_age_seconds(activity_at)

    # 进程心跳是「主循环还在转」；活动心跳是「最近一次真正跑完的任务」。
    # 只看前者会漏掉「线程池卡死但循环还活着」——那正是绿灯骗人的姿势。
    problems: List[str] = []
    scheduler_running = hb_age is not None and hb_age < HEARTBEAT_STALE_SECONDS
    if not scheduler_running:
        if hb_age is None:
            problems.append("调度器从未写过心跳，进程可能没起来")
        else:
            problems.append(f"调度器心跳已过期 {hb_age} 秒（阈值 {HEARTBEAT_STALE_SECONDS} 秒）")

    rules = (
        db.query(Rule)
        .filter(Rule.is_enabled.is_(True), Rule.schedule_type.in_(["interval", "cron"]))
        .all()
    )

    # One query for the latest execution per rule (was N+1).
    last_by_rule: dict = {}
    recent_rows = []
    if rules:
        rule_ids = [r.id for r in rules]
        rows = (
            db.query(RuleExecutionLog)
            .filter(RuleExecutionLog.rule_id.in_(rule_ids))
            .order_by(RuleExecutionLog.rule_id.asc(), RuleExecutionLog.executed_at.desc())
            .all()
        )
        for row in rows:
            last_by_rule.setdefault(row.rule_id, row)
            recent_rows.append(row)

    now = local_now()
    cutoff_24h = now - timedelta(hours=24)
    jobs = []
    stale_rules = 0
    consecutive_failures_max = 0
    for r in rules:
        last_log = last_by_rule.get(r.id)
        last_status = last_log.status if last_log else None
        schedule = f"{r.schedule_type}: {r.schedule_value}"

        # 调度参数非法 → 这条规则根本没挂上调度器
        schedule_error = None
        try:
            from app.services.rule_runner import ScheduleError, parse_schedule
            parse_schedule(r.schedule_type, r.schedule_value)
        except Exception as exc:  # ScheduleError 都算
            schedule_error = str(exc)
            problems.append(f"「{r.name}」调度参数非法，已跳过排期：{schedule_error}")

        # 连续失败：从最近一条往前数 success 就停
        streak = 0
        for row in recent_rows:
            if row.rule_id != r.id:
                continue
            if row.status == "error":
                streak += 1
            else:
                break
        consecutive_failures_max = max(consecutive_failures_max, streak)
        if streak >= 3:
            problems.append(f"「{r.name}」已连续失败 {streak} 次")

        is_stale = False
        if r.next_run and r.next_run < now - timedelta(minutes=10):
            is_stale = True
            stale_rules += 1
            problems.append(f"「{r.name}」下次执行时间已过（{format_dt(r.next_run)}），可能没被调度")

        jobs.append({
            "id": f"rule_{r.id}",
            "rule_id": r.id,
            "name": r.name,
            "next_run": format_dt(r.next_run),
            "last_run": format_dt(last_log.executed_at) if last_log else None,
            "last_status": last_status,
            "duration_ms": (last_log.duration_ms or 0) if last_log else 0,
            "triggered_by": (last_log.triggered_by or "") if last_log else "",
            "schedule": schedule,
            "schedule_error": schedule_error,
            "stale": is_stale,
            "consecutive_failures": streak,
            "is_enabled": bool(r.is_enabled),
        })

    # 内置的保留清理任务不在 rules 表里，但调度器里挂着 —— 不列出来的话
    # 「任务数」永远少一个，还以为丢了。时间用 rule_runner 那条预览路径算。
    try:
        from app.services.rule_runner import preview_schedule
        _ret = preview_schedule("cron", "17 3 * * *", count=1)
        _ret_next = (_ret.get("next_runs") or [None])[0]
    except Exception:
        _ret_next = None
    jobs.append({
        "id": "retention_daily",
        "rule_id": None,
        "name": "每日数据保留清理",
        "next_run": _ret_next,
        "last_run": None,
        "last_status": None,
        "duration_ms": 0,
        "triggered_by": "scheduler",
        "schedule": "cron: 17 3 * * *",
        "schedule_error": None,
        "stale": False,
        "consecutive_failures": 0,
        "is_enabled": True,
    })

    # 近 24h 执行统计（含漏跑）。**不跟规则表挂钩** —— 规则被删了它跑过的痕迹
    # 还在，只数当前启用规则会把历史统计抹掉。
    counts = {"success": 0, "error": 0, "missed": 0}
    status_rows = (
        db.query(RuleExecutionLog.status, func.count(RuleExecutionLog.id))
        .filter(RuleExecutionLog.executed_at >= cutoff_24h)
        .group_by(RuleExecutionLog.status)
        .all()
    )
    for status_name, n in status_rows:
        key = status_name if status_name in counts else "success"
        counts[key] += int(n)

    return {
        "running": scheduler_running,
        "heartbeat_at": heartbeat_at or None,
        "heartbeat_age_seconds": hb_age,
        "last_activity_at": activity_at or None,
        "last_activity_age_seconds": act_age,
        "stale_threshold_seconds": HEARTBEAT_STALE_SECONDS,
        "stale_rules": stale_rules,
        "consecutive_failures_max": consecutive_failures_max,
        "counts_24h": counts,
        "jobs": jobs,
        "problems": problems,
        "healthy": scheduler_running and not problems,
    }


@app.get("/api/scheduler/status", dependencies=[Depends(get_current_user)])
async def scheduler_status(db=Depends(get_db)):
    """Scheduler status from DB heartbeat + rule table.

    Replaces the old `pgrep -f run_scheduler.py` subprocess call (which also
    leaked process info to unauthenticated callers). The scheduler writes a
    `scheduler_heartbeat` SystemConfig row on every tick; if that goes stale we
    report the scheduler as down.

    ``problems`` 里写清「为什么不健康」—— 只回一个 running: false 的红点，
    用户看到的是「坏了」，但不知道该去修什么。
    """
    from app.schemas.common import Response

    return Response(data=_scheduler_snapshot(db))


@app.get("/api/scheduler/health", dependencies=[Depends(get_current_user)])
async def scheduler_health(db=Depends(get_db)):
    """调度器健康检查：毛病清单 + 近 24h 执行统计。给调度中心页顶部的健康条用。"""
    from app.schemas.common import Response

    snap = _scheduler_snapshot(db)
    return Response(data={
        "healthy": snap["healthy"],
        "running": snap["running"],
        "problems": snap["problems"],
        "stale_rules": snap["stale_rules"],
        "consecutive_failures_max": snap["consecutive_failures_max"],
        "counts_24h": snap["counts_24h"],
        "heartbeat_at": snap["heartbeat_at"],
        "heartbeat_age_seconds": snap["heartbeat_age_seconds"],
        "last_activity_at": snap["last_activity_at"],
        "last_activity_age_seconds": snap["last_activity_age_seconds"],
        "job_count": len(snap["jobs"]),
    })


@app.get("/metrics")
async def metrics(db=Depends(get_db), token: str = ""):
    """Prometheus 文本格式导出（手写，不引 prometheus_client）。

    刻意不引依赖 —— 容器的 venv 是 build 时装的，deploy.sh 不会重装。
    若 `system_config.metrics_token` 非空，则要求 `?token=`；
    为空时开放（内网抓取场景）。指标里只放计数和时长，不放规则名/查询语句。
    """
    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse
    from app.models.config import SystemConfig

    row = db.query(SystemConfig).filter(SystemConfig.key == "metrics_token").first()
    expected = (row.value if row else "") or ""
    if expected:
        provided = token or ""
        if not provided:
            raise HTTPException(status_code=401, detail="缺少 metrics token")
        if provided != expected:
            raise HTTPException(status_code=403, detail="metrics token 不匹配")

    snap = _scheduler_snapshot(db)
    hb_age = snap["heartbeat_age_seconds"]
    act_age = snap["last_activity_age_seconds"]
    lines = [
        "# HELP scheduler_up 调度器进程心跳是否新鲜（1=是）",
        "# TYPE scheduler_up gauge",
        f"scheduler_up {1 if snap['running'] else 0}",
        "# HELP scheduler_heartbeat_age_seconds 进程心跳距今秒数",
        "# TYPE scheduler_heartbeat_age_seconds gauge",
        f"scheduler_heartbeat_age_seconds {hb_age if hb_age is not None else -1}",
        "# HELP scheduler_last_activity_age_seconds 最近一次任务跑完距今秒数",
        "# TYPE scheduler_last_activity_age_seconds gauge",
        f"scheduler_last_activity_age_seconds {act_age if act_age is not None else -1}",
        "# HELP scheduler_jobs 已排期任务数（含内置 retention）",
        "# TYPE scheduler_jobs gauge",
        f"scheduler_jobs {len(snap['jobs'])}",
        "# HELP scheduler_stale_rules next_run 已过期的规则数",
        "# TYPE scheduler_stale_rules gauge",
        f"scheduler_stale_rules {snap['stale_rules']}",
        "# HELP rule_runs_24h 近 24 小时执行次数，按 status 分",
        "# TYPE rule_runs_24h gauge",
    ]
    for status, n in snap["counts_24h"].items():
        lines.append(f'rule_runs_24h{{status="{status}"}} {n}')
    lines.append(f'rule_missed_24h {snap["counts_24h"].get("missed", 0)}')

    # 按规则：只用数字 id 当 label —— 规则名会把基数炸掉，也别把查询语句吐给监控。
    lines.append("# HELP rule_last_success_timestamp 规则最近一次成功执行的时间戳（秒）")
    lines.append("# TYPE rule_last_success_timestamp gauge")
    lines.append("# HELP rule_last_run_duration_seconds 规则最近一次执行耗时（秒）")
    lines.append("# TYPE rule_last_run_duration_seconds gauge")
    lines.append("# HELP rule_consecutive_failures 规则连续失败次数")
    lines.append("# TYPE rule_consecutive_failures gauge")
    for job in snap["jobs"]:
        rid = job.get("rule_id")
        if rid is None:
            continue
        ts = "0"
        if job.get("last_status") == "success" and job.get("last_run"):
            try:
                from datetime import datetime
                ts = str(int(datetime.strptime(job["last_run"], "%Y-%m-%d %H:%M:%S").timestamp()))
            except (ValueError, TypeError):
                ts = "0"
        lines.append(f'rule_last_success_timestamp{{rule_id="{rid}"}} {ts}')
        lines.append(
            f'rule_last_run_duration_seconds{{rule_id="{rid}"}} '
            f"{(job.get('duration_ms') or 0) / 1000.0:.3f}"
        )
        lines.append(
            f'rule_consecutive_failures{{rule_id="{rid}"}} {job.get("consecutive_failures") or 0}'
        )

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=settings.DEBUG)
