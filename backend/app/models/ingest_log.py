from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index

from app.models.base import Base


class IngestLog(Base):
    """接收接口收到的原始数据"""

    __tablename__ = 'ingest_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey('ingest_endpoints.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint_name = Column(String(64), nullable=False, index=True)
    payload = Column(Text, nullable=True, comment='源端推送的原始数据（JSON 文本）')
    received_at = Column(DateTime, default=datetime.now, index=True)


Index('ix_ingest_logs_endpoint_received', IngestLog.endpoint_id, IngestLog.received_at)
