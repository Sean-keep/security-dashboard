"""
Nightly retention / housekeeping.

These tables grow without bound: ingest_logs especially (one row per remote
push), then rule_execution_logs (one per rule run). Left alone they eventually
eat the MySQL volume and make every list query slower. There is no Alembic
here, so the day-counts live in SystemConfig and default to the values below.
"""
from datetime import timedelta

from app.models.alert import Alert
from app.models.base import SessionLocal
from app.models.config import SystemConfig
from app.models.execution_log import RuleExecutionLog
from app.models.ingest_log import IngestLog
from app.models.operation_log import OperationLog
from app.models.remote_execution import RemoteExecution
from app.models.user import LoginLog
from app.utils.timezone import local_now

# key -> (model, column, default_days)
# 0 = 保留该表不清理（安全默认；要清就去系统配置里填天数）
DEFAULTS = {
    "retention_ingest_logs_days": (IngestLog, IngestLog.received_at, 30),
    "retention_execution_logs_days": (RuleExecutionLog, RuleExecutionLog.executed_at, 30),
    "retention_operation_logs_days": (OperationLog, OperationLog.created_at, 90),
    "retention_login_logs_days": (LoginLog, LoginLog.created_at, 90),
    "retention_remote_executions_days": (RemoteExecution, RemoteExecution.created_at, 30),
    "retention_alerts_resolved_days": (Alert, Alert.created_at, 180),
}


def _days(db, key: str) -> int:
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None or not str(row.value or "").strip():
        return DEFAULTS[key][2]
    try:
        return max(0, int(str(row.value).strip()))
    except ValueError:
        return DEFAULTS[key][2]


def run_retention(db=None) -> dict:
    """按配置天数删旧数据。返回 {table: deleted_rows}。

    ``db`` 可注入（测试用）；默认开一个自己的 session。
    """
    owns = db is None
    if owns:
        db = SessionLocal()
    deleted: dict = {}
    try:
        for key, (model, col, _default) in DEFAULTS.items():
            days = _days(db, key)
            if days <= 0:
                continue
            cutoff = local_now() - timedelta(days=days)
            try:
                if model is Alert:
                    # 告警只清「已结束」的；pending/confirmed 是在办案件，不碰
                    n = (
                        db.query(Alert)
                        .filter(Alert.created_at < cutoff, Alert.status.in_(("resolved", "false_positive")))
                        .delete(synchronize_session=False)
                    )
                else:
                    n = db.query(model).filter(col < cutoff).delete(synchronize_session=False)
                db.commit()
                if n:
                    deleted[model.__tablename__] = n
            except Exception as exc:
                # 单表失败不该拖垮整批：一张表没建好 / 没权限，其它表还得清。
                try:
                    db.rollback()
                except Exception:
                    pass
                print(f"[Retention] {model.__tablename__} skipped: {exc}")
    finally:
        if owns:
            db.close()
    return deleted
