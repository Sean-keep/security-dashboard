"""
Metric rule sustain state —— 「条件连续成立满 N 分钟」的计时器，一行一个 series。

为什么必须落库而不是留在进程里：uvicorn（web）和 run_scheduler.py 是两个进程，
APScheduler 的 JobStore 又是内存型的，调度器一重启就把计时清零 —— 「持续 5 分钟」
会永远凑不满。状态跟告警去重（`rule_executor` 的 fingerprint）一样，是跨运行的
事实，只有数据库靠得住。

一行 = 一条规则的一条 Prometheus series（`series_key` 是标签集的稳定指纹）。
series 消失或规则删除/停用/改条件时清掉，避免临时性 series（pod 名之类）留垃圾。
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from app.models.base import Base, TimestampMixin


class RuleMetricState(Base, TimestampMixin):
    __tablename__ = "rule_metric_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False, index=True)

    # sha1(标签集规范 JSON)。多台机器同时超阈值是多条独立计时，靠它区分。
    series_key = Column(String(64), nullable=False)
    # 完整标签集 JSON，拼告警文案用（instance / job / cpu …）。
    series_labels = Column(Text, default="{}")

    # 条件首次成立时间。NULL = 当前未超阈值（时钟归零，等下一次成立重新开始）。
    breach_since = Column(DateTime, nullable=True)
    # 是否已经发出过告警。区分「还没凑满时长就回落」和「告警过、现在恢复」——
    # 少了它会发一堆莫名其妙的「已恢复」。
    firing = Column(Integer, default=0)
    last_value = Column(Float, nullable=True)
    last_check_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("rule_id", "series_key", name="uq_metric_state_rule_series"),
    )

    def __repr__(self):
        return (
            f"<RuleMetricState(rule_id={self.rule_id}, series_key='{self.series_key[:8]}', "
            f"firing={self.firing})>"
        )
