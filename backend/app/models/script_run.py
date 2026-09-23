"""
ScriptRunLog — who ran which script, when, and what came out.

Before this, script execution left no audit trail at all: an admin could run
anything through `/api/inspect/scripts/execute` and the only record was a
transient HTTP response. For a security dashboard that is the wrong default.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.models.base import Base, LongText
from app.utils.timezone import local_now


class ScriptRunLog(Base):
    __tablename__ = "script_run_logs"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    script_id = Column(Integer, nullable=True, index=True)
    script_name = Column(String(128), default="")
    # content 的 sha256 前 16 位：脚本内容改了之后，历史记录还能对上「当时跑的是哪一版」
    script_version_hash = Column(String(32), default="", index=True)
    script_type = Column(String(32), default="python")

    run_by = Column(String(64), default="", index=True)
    trigger = Column(String(32), default="manual")  # manual | adhoc | block

    exit_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    # 只留尾巴，不是全量 —— stdout 可以是任意长度
    stdout_tail = Column(LongText, default="")
    stderr_tail = Column(LongText, default="")
    error = Column(Text, default="")

    started_at = Column(DateTime, default=local_now, index=True)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ScriptRunLog(id={self.id}, script_id={self.script_id}, exit={self.exit_code})>"
