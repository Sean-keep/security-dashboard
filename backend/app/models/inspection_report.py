"""
Inspection Report Model - 巡检报告存储
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from app.models.base import Base


class InspectionReport(Base):
    """巡检报告"""
    __tablename__ = "inspection_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(String(20), nullable=False, index=True)           # 报告日期 YYYY-MM-DD
    generated_at = Column(String(30), nullable=False)                       # 生成时间 CST
    address_count = Column(Integer, default=0)
    script_count = Column(Integer, default=0)
    # 完整报告内容 JSON（存储可预览的摘要；不含 scripts stdout 以控制体积）
    # MEDIUMTEXT ≈ 16MB，足够存储完整报告内容
    content = Column(MEDIUMTEXT, nullable=False)
    # 原始 scripts stdout 用于导出
    scripts_json = Column(MEDIUMTEXT, nullable=True)
    created_by = Column(String(100), default="admin")
    created_at = Column(DateTime, default=datetime.now, index=True)
