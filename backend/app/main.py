"""
Security Dashboard Backend - FastAPI Application
"""
from contextlib import asynccontextmanager
from datetime import timedelta

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


@app.get("/api/scheduler/status", dependencies=[Depends(get_current_user)])
async def scheduler_status(db=Depends(get_db)):
    """Scheduler status from DB heartbeat + rule table.

    Replaces the old `pgrep -f run_scheduler.py` subprocess call (which also
    leaked process info to unauthenticated callers). The scheduler writes a
    `scheduler_heartbeat` SystemConfig row on every tick; if that goes stale we
    report the scheduler as down.
    """
    from app.models.config import SystemConfig
    from app.models.rule import Rule
    from app.models.execution_log import RuleExecutionLog
    from app.schemas.common import Response
    from app.utils.timezone import format_dt, local_now

    heartbeat = db.query(SystemConfig).filter(SystemConfig.key == "scheduler_heartbeat").first()
    heartbeat_at = heartbeat.value if heartbeat else ""
    scheduler_running = False
    if heartbeat_at:
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(heartbeat_at)
            scheduler_running = (local_now() - ts) < timedelta(minutes=5)
        except ValueError:
            scheduler_running = False

    rules = (
        db.query(Rule)
        .filter(Rule.is_enabled.is_(True), Rule.schedule_type.in_(["interval", "cron"]))
        .all()
    )

    # One query for the latest execution per rule (was N+1).
    last_by_rule: dict = {}
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

    jobs = []
    for r in rules:
        last_log = last_by_rule.get(r.id)
        jobs.append({
            "id": f"rule_{r.id}",
            "name": r.name,
            "next_run": format_dt(r.next_run),
            "last_run": format_dt(last_log.executed_at) if last_log else None,
            "last_status": last_log.status if last_log else None,
            "schedule": f"{r.schedule_type}: {r.schedule_value}",
        })

    return Response(data={
        "running": scheduler_running,
        "heartbeat_at": heartbeat_at or None,
        "jobs": jobs,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=settings.DEBUG)
