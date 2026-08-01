from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.models.base import Base


class IngestEndpoint(Base):
    """自定义 API 接收接口（源端往 /api/remote/ingest/{name} 推送数据即自动存储）"""

    __tablename__ = 'ingest_endpoints'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, index=True, nullable=False, comment='接口名称（URL 路径段，唯一）')
    description = Column(Text, nullable=True, comment='接口说明')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
