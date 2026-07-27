"""
Custom Metric Model - User-defined Grafana/Prometheus queries
"""
from sqlalchemy import Column, Integer, String, Text
from app.models.base import Base, TimestampMixin


class CustomMetric(Base, TimestampMixin):
    """User-defined custom metric query"""
    __tablename__ = "custom_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, default="")
    promql = Column(Text, nullable=False)  # PromQL expression
    unit = Column(String(32), default="")  # e.g. "%", "ms", "req/s"

    def __repr__(self):
        return f"<CustomMetric(id={self.id}, name='{self.name}')>"
