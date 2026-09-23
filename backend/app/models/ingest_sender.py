"""
Ingest Sender — 接收端认人

远程端脚本已经写死不能改，所以「身份」只能由接收端从第一包特征里认：
源 IP / User-Agent / Content-Type / 载荷形状。这些是**给管理员看的提示，
不是凭证** —— 能连到端口就能伪造。

绑定只是给发送方起名字、留个识别记录，**不是**进日报的闸门。日报勾了哪个
接口就要它最近一条数据，跟 token 和绑定都无关。
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.models.base import Base
from app.utils.timezone import local_now


class IngestSender(Base):
    """某个接收接口下、按第一包特征聚出来的发送方"""

    __tablename__ = "ingest_senders"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "fingerprint", name="uq_ingest_senders_endpoint_fp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey("ingest_endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_name = Column(String(64), nullable=False, index=True)
    # sha1(src_ip|user_agent|content_type|payload_shape)
    fingerprint = Column(String(64), nullable=False, index=True)

    # 第一包特征，全部原样存下来给管理员判断「这是谁」
    src_ip = Column(String(64), default="", comment="源 IP")
    user_agent = Column(String(256), default="", comment="User-Agent")
    content_type = Column(String(128), default="", comment="Content-Type")
    payload_shape = Column(String(256), default="", comment="载荷顶层字段名（识别提示，可伪造）")

    display_name = Column(String(128), default="", comment="管理员绑定时起的名字")
    # pending = 还没认；bound = 认了（起了名字）；rejected = 标成不要的
    # 纯标注，不影响日报 —— 日报只看接口勾选
    status = Column(String(16), default="pending", index=True)
    sample_payload = Column(Text, nullable=True, comment="第一包载荷，供绑定时辨认")
    send_count = Column(Integer, default=0)
    first_seen_at = Column(DateTime, default=local_now)
    last_seen_at = Column(DateTime, default=local_now, index=True)
    bound_at = Column(DateTime, nullable=True)


Index("ix_ingest_senders_endpoint_status", IngestSender.endpoint_id, IngestSender.status)
