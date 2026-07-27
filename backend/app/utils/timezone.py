"""
Timezone utilities - format datetimes consistently
Container timezone is Asia/Shanghai (CST, UTC+8), so datetime.now() returns CST.
"""
from datetime import datetime
from typing import Optional

def format_dt(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime to string using CST timezone."""
    if dt is None:
        return None
    try:
        return dt.strftime(fmt)
    except:
        return str(dt)

def now_cst() -> datetime:
    """Get current time (already CST as container is Asia/Shanghai)."""
    return datetime.now()
