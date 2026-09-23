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
    # 存活信号：没有它就分不清「agent 挂了」和「本来就没数据」。
    # 与 scheduler_heartbeat 同一个思路 —— 时间戳变陈旧即视为静默。
    last_received_at = Column(DateTime, nullable=True, comment='最近一次成功接收时间')
    created_at = Column(DateTime, default=local_now)
    updated_at = Column(DateTime, default=local_now, onupdate=local_now)
