from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.models.base import Base
from app.utils.timezone import local_now


class IngestLog(Base):
    """接收接口收到的原始数据"""

    __tablename__ = 'ingest_logs'
    # 幂等：同一 (endpoint, message_id) 只存一行。MySQL/SQLite 的唯一索引都允许多个
    # NULL，所以没带 X-Message-Id 的推送（旧源端）不受影响。
    __table_args__ = (
        UniqueConstraint('endpoint_id', 'message_id', name='uq_ingest_logs_endpoint_msg'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey('ingest_endpoints.id', ondelete='CASCADE'), nullable=False, index=True)
    endpoint_name = Column(String(64), nullable=False, index=True)
    # 归属发送方。绑定与否看 ingest_senders.status —— 只有 bound 的进日报。
    sender_id = Column(Integer, ForeignKey('ingest_senders.id', ondelete='SET NULL'), nullable=True, index=True)
    payload = Column(Text, nullable=True, comment='源端推送的原始数据（JSON 文本）')
    # 源端声明的发送时间（X-Sent-At）。接收端的 received_at 只反映到达顺序，
    # 重试送达的旧批次会排在新批次后面 —— 取「最新一条」时必须优先用它。
    sent_at = Column(DateTime, nullable=True, index=True, comment='源端发送时间 X-Sent-At')
    # 源端声明的幂等键（X-Message-Id）
    message_id = Column(String(128), nullable=True, comment='源端幂等键 X-Message-Id')
    received_at = Column(DateTime, default=local_now, index=True)


Index('ix_ingest_logs_endpoint_received', IngestLog.endpoint_id, IngestLog.received_at)
Index('ix_ingest_logs_endpoint_sent', IngestLog.endpoint_id, IngestLog.sent_at)
