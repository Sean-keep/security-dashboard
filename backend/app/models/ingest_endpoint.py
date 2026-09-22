from sqlalchemy import Column, DateTime, Integer, String, Text

from app.models.base import Base
from app.utils.timezone import local_now


class IngestEndpoint(Base):
    """自定义 API 接收接口（源端往 /api/remote/ingest/{name} 推送数据即自动存储）"""

    __tablename__ = 'ingest_endpoints'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, index=True, nullable=False, comment='接口名称（URL 路径段，唯一）')
    description = Column(Text, nullable=True, comment='接口说明')
    # Shared secret presented by the source as X-Ingest-Token. create_all() adds
    # the column on bootstrap; live upgrades need the migration in docs/.
    token = Column(String(64), nullable=True, index=True, comment='推送密钥（X-Ingest-Token）')
    created_at = Column(DateTime, default=local_now)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now)
