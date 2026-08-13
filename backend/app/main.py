"""
Security Dashboard Backend - FastAPI Application
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.models.base import init_db
from app.api import auth, addresses, rules, alerts, settings as settings_api
from app.api.inspect import router as inspect_router
from app.api.reports import router as reports_router
from app.api.remote import router as remote_router
from app.api.execution_logs import router as execution_logs_router
from app.api.logs import router as logs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    print(f"📦 Database: {'SQLite' if settings.USE_SQLITE else 'MySQL'}")
    print(f"🔍 ES: {settings.ES_HOST}:{settings.ES_PORT}")

    # Initialize database
    init_db()

    # 一次性迁移：将历史登录日志（login_logs）同步到日志中心（operation_logs）
    try:
        from app.models.base import SessionLocal as _SL
        from app.models.user import LoginLog as _LoginLog
        from app.models.operation_log import OperationLog as _OperationLog
        _mig_db = _SL()
        try:
            _has_login = _mig_db.query(_OperationLog).filter(
                _OperationLog.log_type == "login"
            ).first()
            if not _has_login:
                _old_logs = _mig_db.query(_LoginLog).order_by(_LoginLog.created_at.asc()).all()
                for _ll in _old_logs:
                    _mig_db.add(_OperationLog(
                        log_type="login",
                        username=_ll.username or "",
                        action="登录",
                        ip_address=_ll.ip_address,
                        status="success" if _ll.status == "success" else "failure",
                        detail=_ll.reason or "",
                        created_at=_ll.created_at
                    ))
                _mig_db.commit()
                if _old_logs:
                    print(f"✅ 已迁移 {len(_old_logs)} 条历史登录日志到日志中心")
        finally:
            _mig_db.close()
    except Exception as _e:
        print(f"⚠️ 登录日志迁移失败: {_e}")

    # 确保 Prometheus 相关配置 key 存在（默认值）
    try:
        from app.models.base import SessionLocal
        from app.models.config import SystemConfig
        _cfg_db = SessionLocal()
        try:
            _prom_defaults = [
                ("prometheus_url", "http://localhost:9090", "Prometheus 地址", "Prometheus 服务地址", "prometheus"),
                ("prometheus_user", "", "Prometheus 用户名", "Basic Auth 用户名（可选）", "prometheus"),
                ("prometheus_password", "", "Prometheus 密码", "Basic Auth 密码（可选）", "prometheus"),
            ]
                # Elasticsearch
                ("es_host", "", "ES 地址", "Elasticsearch 主机地址", "es"),
                ("es_port", "9200", "ES 端口", "Elasticsearch 端口", "es"),
                ("es_scheme", "https", "ES 协议", "http 或 https", "es"),
                ("es_verify_certs", "false", "ES 验证证书", "https 时是否验证证书 (true/false)", "es"),
                ("es_user", "", "ES 用户名", "Elasticsearch 用户名（可选）", "es"),
                ("es_password", "", "ES 密码", "Elasticsearch 密码（可选）", "es"),
                ("es_index", "security-logs-*", "ES 索引", "查询使用的索引通配符", "es"),
                # MySQL
                ("mysql_host", "localhost", "MySQL 地址", "MySQL 主机地址", "mysql"),
                ("mysql_port", "3306", "MySQL 端口", "MySQL 端口", "mysql"),
                ("mysql_user", "root", "MySQL 用户", "MySQL 用户名", "mysql"),
                ("mysql_password", "", "MySQL 密码", "MySQL 密码", "mysql"),
                ("mysql_database", "security_dashboard", "MySQL 数据库", "数据库名", "mysql"),
                # Grafana
                ("grafana_url", "", "Grafana 地址", "Grafana URL，如 http://192.168.1.100:3000", "grafana"),
                ("grafana_auth_mode", "apikey", "Grafana 认证方式", "apikey 或 basic", "grafana"),
                ("grafana_api_key", "", "Grafana API Key", "API Key（可选）", "grafana"),
                ("grafana_user", "", "Grafana 用户名", "Basic Auth 用户名（可选）", "grafana"),
                ("grafana_password", "", "Grafana 密码", "Basic Auth 密码（可选）", "grafana"),
            for _key, _val, _label, _desc, _grp in _prom_defaults:
                if not _cfg_db.query(SystemConfig).filter(SystemConfig.key == _key).first():
                    _cfg_db.add(SystemConfig(
                        key=_key, value=_val, label=_label,
                        description=_desc, group_name=_grp
                    ))
            _cfg_db.commit()
            print("✅ Prometheus 配置初始化完成")
        finally:
            _cfg_db.close()
    except Exception as _e:
        print(f"⚠️ 初始化 Prometheus 配置失败: {_e}")

    # 调度器由独立进程运行（run_scheduler.py），不在 web worker 中启动
    print("ℹ️ 调度器由独立进程运行")

    yield

    # Shutdown
    print("👋 Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(addresses.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(execution_logs_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(reports_router)
app.include_router(inspect_router)
app.include_router(remote_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/scheduler/status")
async def scheduler_status():
    """调度器状态检查（如果停止则自动重启）"""
    try:
        from app.services.scheduler_service import scheduler_service
        
        # 调度器由独立进程运行，这里只查询状态
        jobs = scheduler_service.scheduler.get_jobs()
        return {
            "running": scheduler_service.scheduler.running,
            "jobs": [{"id": j.id, "name": j.name, "next_run": str(j.next_run_time)} for j in jobs]
        }
    except Exception as e:
        return {"error": str(e), "running": False, "jobs": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=settings.DEBUG
    )
