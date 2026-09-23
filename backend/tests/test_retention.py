"""Nightly retention must prune old rows and leave live cases alone.

Before this, ingest_logs and rule_execution_logs grew forever. Also: alerts are
case files — only `resolved` / `false_positive` get pruned, never `pending`.
"""
from datetime import timedelta

from app.models.alert import Alert
from app.models.base import SessionLocal
from app.models.config import SystemConfig
from app.models.execution_log import RuleExecutionLog
from app.models.ingest_endpoint import IngestEndpoint
from app.models.ingest_log import IngestLog
from app.models.operation_log import OperationLog
from app.utils.timezone import local_now


def _set_days(db, key, val):
    row = db.query(SystemConfig).filter(SystemConfig.key == key).first()
    if row is None:
        db.add(SystemConfig(key=key, value=str(val), label=key, group_name="retention"))
    else:
        row.value = str(val)
    db.commit()


def test_retention_prunes_old_ingest_and_execution_logs(db_session):
    old = local_now() - timedelta(days=40)
    ep = IngestEndpoint(name="ret1", description="")
    db_session.add(ep)
    db_session.commit()
    db_session.add(IngestLog(endpoint_id=ep.id, endpoint_name="ret1", payload="{}", received_at=old))
    db_session.add(IngestLog(endpoint_id=ep.id, endpoint_name="ret1", payload="{}", received_at=local_now()))
    db_session.add(RuleExecutionLog(rule_id=1, rule_name="r", executed_at=old))
    db_session.add(RuleExecutionLog(rule_id=1, rule_name="r", executed_at=local_now()))
    db_session.commit()

    _set_days(db_session, "retention_ingest_logs_days", 30)
    _set_days(db_session, "retention_execution_logs_days", 30)

    from app.services.retention import run_retention

    # run_retention opens its own SessionLocal; point that at the same engine.
    import app.models.base as base
    import app.services.retention as ret

    assert ret.IngestLog is IngestLog
    deleted = run_retention(db_session)
    assert deleted.get("ingest_logs") == 1
    assert deleted.get("rule_execution_logs") == 1
    assert db_session.query(IngestLog).count() == 1
    assert db_session.query(RuleExecutionLog).count() == 1


def test_retention_never_touches_open_alerts(db_session):
    old = local_now() - timedelta(days=400)
    for status in ("pending", "confirmed", "resolved", "false_positive"):
        db_session.add(Alert(title=f"a-{status}", status=status, created_at=old, last_seen_at=old))
    db_session.commit()

    _set_days(db_session, "retention_alerts_resolved_days", 180)

    from app.services.retention import run_retention

    run_retention(db_session)
    left = {a.status for a in db_session.query(Alert).all()}
    assert left == {"pending", "confirmed"}, left


def test_zero_days_means_never_prune(db_session):
    old = local_now() - timedelta(days=4000)
    db_session.add(OperationLog(log_type="operation", action="x", created_at=old))
    db_session.commit()

    _set_days(db_session, "retention_operation_logs_days", 0)

    from app.services.retention import run_retention

    run_retention(db_session)
    assert db_session.query(OperationLog).count() == 1
