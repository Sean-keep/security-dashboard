"""
Timezone utilities.

Storage convention in this project:
- DB timestamps are **naive local time** (container TZ = Asia/Shanghai). MySQL
  sessions are opened with `time_zone='+08:00'` so the driver and the column
  values agree. Keep using `local_now()` for anything written to a model.
- JWT `exp` is a UTC instant (RFC 7519). Use `utc_now()` there only.
- Elasticsearch stores UTC. Use `utc_now()` / `utc_iso()` for query windows.
"""
from datetime import datetime, timezone
from typing import Optional


def local_now() -> datetime:
    """Naive local timestamp (Asia/Shanghai) — use for all DB writes."""
    return datetime.now()


def utc_now() -> datetime:
    """Aware UTC timestamp — use for JWT and anything compared to UTC instants."""
    return datetime.now(timezone.utc)


def utc_naive() -> datetime:
    """Naive UTC timestamp — for ES range filters that get ``isoformat()+'Z'``."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: Optional[datetime] = None) -> str:
    """ISO-8601 UTC string with a trailing Z (ES-friendly)."""
    if dt is None:
        dt = utc_naive()
    elif dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def format_dt(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a naive local datetime for display (Asia/Shanghai)."""
    if dt is None:
        return None
    try:
        return dt.strftime(fmt)
    except Exception:
        return str(dt)


# Backwards-compatible aliases
def now_cst() -> datetime:
    return local_now()
