"""
指标阈值规则的状态机 —— 「条件连续成立满 N 分钟」的唯一实现。

## 为什么不能写成 `avg_over_time(cpu[5m]) > 80`

那是「5 分钟**均值**超 80」：一个尖峰然后立刻掉下去也能触发。用户要的是
「持续 5 分钟都在 80 以上」——中间任何一次掉下阈值就该**重新计时**。所以必须
每分钟查一次 instant 值，自己记「从什么时候起一直成立」。

## 状态为什么必须落库

uvicorn（web）和 `run_scheduler.py`（调度器）是两个进程，APScheduler 的 JobStore
又在内存里。计时器留在进程里，调度器一重启就清零，「持续 5 分钟」永远凑不满。
所以每个 (rule, series) 一行 `RuleMetricState`，见 `models/metric_rule_state.py`。

## 状态机（每 60 秒一次）

```
for s in 返回的每条 series:                # 每条 series 独立计时
    if not 超阈值:
        if 已告警: 发「已恢复」+ 关告警
        清零计时
        continue
    if 计时器未启动: 启动
    if 未告警 and 已持续 >= N 分钟:
        标记已告警 + 产出结果行            # 冷却去重交给 rule_executor
    elif 已告警:
        产出结果行                          # 持续中，靠去重冷却压噪音

for 上一轮有、这一轮没返回的 series:        # exporter 挂了 / 实例下线
    if 已告警: 发「已恢复（数据中断）」+ 关告警
    删掉状态行                              # 临时性 series 不留垃圾
```

`firing` 这个标志是必需的：「条件成立但还没凑满时长」就回落时**不能**发恢复通知
（本来就没告警过）。少了它会发一堆莫名其妙的「已恢复」。

## 两条刻意取舍

* **查询失败一律不动状态**（`no_data`）。Grafana 抖一下不该重置计时，更不该
  把规则判失败 —— 用户明确要「不误报也不算失败」。
* **观测断档超过 GRACE 就重新计时**。中间那一小时没查到，「连续成立」无从证明，
  宁可漏报也不该凭空宣称「已持续 5 分钟」。已经在告警的不受影响（关掉比留着更糟）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.utils.timezone import local_now

# 调度间隔是 60 秒（服务端强制），连续两次观测跨过这个窗口还算「连续」。
CHECK_INTERVAL_SECONDS = 60
# 断档容忍：3 个周期。misfire_grace_time=300 / coalesce 可能把一次检查推后，
# 跨过这个值就再也无法声称「连续」，只能重新计时。
GRACE_SECONDS = 180

# 比较符。不支持 != —— 阈值告警里「不等于」的语义是「几乎一直成立」，没有告警价值。
OPERATORS = (">", ">=", "<", "<=", "==")

# 身份标签，按具体程度排。机器维度在前，服务/接口维度在后（见 identity_of 的注释）。
# `job` 一定要在里面：`sum by (le, job, route)` 这种聚合下，不带 job 就只剩
# 接口名，同名接口跨服务会撞进同一条告警 —— 也分不清是哪个服务在告警。
_IDENTITY_LABELS = (
    "instance", "node", "pod", "container", "host",
    "service", "job", "route", "path", "endpoint", "url", "api",
)
# 兜底标签：只在没有任何身份标签时才用。
_FALLBACK_LABELS = ("namespace", "app")


# ── 返回结构 ──────────────────────────────────────────────────────


@dataclass
class MetricEvalOutcome:
    """一次检查的结果。``no_data`` 为真时调用方记「无数据」，不告警也不判失败。"""

    no_data: bool = False
    reason: str = ""
    # 只放「又命中了」的结果行 —— `rule_runner` 把这份原样喂给 `process_actions`。
    rows: List[Dict[str, Any]] = field(default_factory=list)
    # 恢复事件。**绝不进 `process_actions`**：那条路的语义是「又命中了 → 开新告警」，
    # 而恢复是它的反面（关掉已经开的告警）。混进去会拿回落后的低于阈值的值
    # 再开一条新单 —— 实测出过「P95 4.8125s（阈值 >5s）反而告警」。
    recoveries: List[Dict[str, Any]] = field(default_factory=list)
    series_seen: int = 0
    breaching: int = 0
    recovered: int = 0

    def to_detail(self) -> Dict[str, Any]:
        """执行日志里那段 JSON。``note`` 是给界面直接显示的中文摘要。"""
        detail: Dict[str, Any] = {
            "total_results": len(self.rows),
            "series_seen": self.series_seen,
            "breaching": self.breaching,
            "recovered": self.recovered,
        }
        if self.no_data:
            detail["no_data"] = True
            detail["note"] = f"无数据：{self.reason}" if self.reason else "无数据"
        return detail


# ── 配置 ──────────────────────────────────────────────────────────


@dataclass
class MetricConfig:
    promql: str = ""
    operator: str = ">"
    threshold: float = 0.0
    duration_seconds: int = 300

    @classmethod
    def from_rule(cls, rule) -> "MetricConfig":
        """从 ``rules.metric_config`` 的 JSON 读配置。坏 JSON 退化成空配置。"""
        raw = getattr(rule, "metric_config", "") or "{}"
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return cls(
            promql=str(data.get("promql") or ""),
            operator=str(data.get("operator") or ">"),
            threshold=_to_float_or(data.get("threshold"), 0.0),
            duration_seconds=int(_to_float_or(data.get("duration_seconds"), 300) or 300),
        )


def _to_float_or(raw, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def compare(value: Optional[float], operator: str, threshold: float) -> bool:
    """指标比较。NaN / None 永远不成立 —— 那不是「没超阈值」，是「没有观测」。"""
    from app.services.metrics_service import is_usable

    if not is_usable(value):
        return False
    v = float(value)  # type: ignore[arg-type]
    if operator == ">":
        return v > threshold
    if operator == ">=":
        return v >= threshold
    if operator == "<":
        return v < threshold
    if operator == "<=":
        return v <= threshold
    if operator == "==":
        return v == threshold
    return False


# ── 结果行（`RuleExecutor` 的契约）────────────────────────────────
#
# `_claim` 读 `src_ip`（回退 ip_address / 攻击地址）和 `count`；
# 模板读任意扁平键；`_write_mysql` 读 start_time/end_time/duration（epoch **毫秒**）；
# 整行会存进 `Alert.raw_log`。
#
# ⚠️ 指纹是 sha1(f"{rule_id}|{ip}|{title}")，所以 `src_ip` 必须能区分 series ——
# 两台机器同时超阈值必须是两条独立告警。


def identity_of(labels: Dict[str, str], key: str) -> str:
    """series 的「身份」，进指纹用。

    指纹是 ``sha1(rule_id|src_ip|title)``，所以这个返回值必须**一条 series 一个值** ——
    撞了就等于两条 series 合并成一条告警，恢复时还会关错单。

    「身份标签」按具体程度排：机器维度（instance/node/pod…）在前，接口维度
    （route/path/endpoint…）在后。同一条 series 上有多个身份标签时**全拼上**
    （``10.0.0.1:9032/v1/login/get_otp``），不然 ``by (le, instance, route)``
    这种聚合下两个接口会被认成同一个身份。只有一个身份标签时保持原值 ——
    ``by (le, route)`` 得到的就是干净的接口名，别硬加后缀。

    ``job``/``namespace`` 只当兜底：它们是「这一批是什么」而不是「这是谁」，
    优先级低于接口名，否则 ``sum by (le, route)`` 会整批落到同一个 job 上。
    """
    labels = labels or {}
    picked = [str(labels[n]) for n in _IDENTITY_LABELS if labels.get(n)]
    if picked:
        if len(picked) == 1:
            return picked[0]
        # 拼接时消掉边界上重复的 `/`：route 一般自带前导斜杠，
        # 直接 join 会拼出 `10.0.0.1:9032//v1/login` 这种难看的身份。
        return "/".join([picked[0]] + [p.lstrip("/") for p in picked[1:]])
    for name in _FALLBACK_LABELS:
        val = labels.get(name, "")
        if val:
            return str(val)
    return f"series-{(key or '')[:12]}"


def series_signature(labels: Dict[str, str]) -> str:
    """紧凑标签签名，拼文案用：``instance="web-01:9100",job="node"``。"""
    items = sorted((labels or {}).items())
    return ",".join(f'{k}="{v}"' for k, v in items)


def build_metric_row(
    cfg: MetricConfig,
    labels: Dict[str, str],
    key: str,
    value: float,
    *,
    breach_since: datetime,
    now: datetime,
) -> Dict[str, Any]:
    """产出一条符合 `RuleExecutor` 契约的结果行。"""
    sustained = max(0, int((now - breach_since).total_seconds()))
    return {
        "src_ip": identity_of(labels, key),
        "instance": labels.get("instance", ""),
        "series": series_signature(labels),
        "labels": dict(labels or {}),
        "promql": cfg.promql,
        "operator": cfg.operator,
        "threshold": cfg.threshold,
        "value": value,
        "sustain_minutes": max(1, int(round(cfg.duration_seconds / 60))),
        "sustained_seconds": sustained,
        "breach_since": breach_since.strftime("%Y-%m-%d %H:%M:%S"),
        "count": 1,
        # _write_mysql 认的是 epoch **毫秒**（datetime.fromtimestamp(x/1000)）
        "start_time": int(breach_since.timestamp() * 1000),
        "end_time": int(now.timestamp() * 1000),
        "duration": sustained,
        "source": "metric_rule",
    }


# ── 状态存取 ──────────────────────────────────────────────────────


def clear_rule_states(db, rule_id: int) -> None:
    """规则删除 / 停用 / 改条件时清掉计时状态。

    状态必须跟着条件走：阈值从 80 改成 70 时，原来那条「已持续 4 分钟」的计时器
    会让新条件一上来就触发 —— 那是拿旧证据判新标准。
    """
    from app.models.metric_rule_state import RuleMetricState

    try:
        db.query(RuleMetricState).filter(RuleMetricState.rule_id == rule_id).delete()
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[MetricRule] clear_rule_states({rule_id}) failed: {exc}")


def _load_states(db, rule_id: int) -> Dict[str, Any]:
    from app.models.metric_rule_state import RuleMetricState

    rows = db.query(RuleMetricState).filter(RuleMetricState.rule_id == rule_id).all()
    return {r.series_key: r for r in rows}


# ── 主入口 ────────────────────────────────────────────────────────


def evaluate_metric_rule(db, rule, *, now: Optional[datetime] = None) -> MetricEvalOutcome:
    """跑一次指标检查：推进计时、产出结果行、处理恢复/消失。

    **不抛异常**（查询失败走 ``no_data``）—— 调用方 `rule_runner.run_rule` 的
    契约是「返回可记账的结果」，而不是让 Grafana 抖动把整条规则判失败。
    """
    from app.services import metrics_service
    from app.models.metric_rule_state import RuleMetricState

    cfg = MetricConfig.from_rule(rule)
    # 计时精度对齐到整秒。`rule_metric_states.breach_since` 是 DATETIME（秒精度），
    # MySQL 写入时会**四舍五入**而不是截断：11:55:52.9 存成 11:55:53，于是下一轮
    # `now - breach_since` 只有 59.9 秒，「持续 1 分钟」硬生生晚一个周期才响
    # （实测 1 分钟规则花 2 分钟触发）。两边都用整秒就没有这个漂移。
    now = (now or local_now()).replace(microsecond=0)
    outcome = MetricEvalOutcome()

    if not cfg.promql.strip():
        outcome.no_data = True
        outcome.reason = "PromQL 表达式为空"
        return outcome

    resp = metrics_service.query_instant(db, cfg.promql)
    if not resp.ok:
        # 查询失败：**一行状态都不写**。既不重置计时，也不触发任何通知。
        outcome.no_data = True
        outcome.reason = resp.error or "查询失败"
        return outcome

    # `seen` 按「序列出现在结果里」算，跟有没有取到值无关 —— NaN 是「序列还在、
    # 这次没值」，不是「序列消失了」。把两者混为一谈会把一条正在告警的 series
    # 误判成数据中断。
    seen: set = set()
    for s in resp.series:
        seen.add(metrics_service.series_key(s.labels))

    if not resp.series:
        outcome.no_data = True
        outcome.reason = "查询无序列"
        # 一次成功但一个序列都没有：全部消失，按数据中断收尾
        outcome.recovered += _gc_vanished(db, rule, seen, cfg, now, outcome)
        db.commit()
        return outcome

    # NaN / 缺值不算观测 —— 既不触发也不算「掉下阈值」
    series = [s for s in resp.series if metrics_service.is_usable(s.value)]
    if not series:
        outcome.no_data = True
        outcome.reason = "序列均无有效取值"
        outcome.series_seen = len(resp.series)
        # 序列还在，只是没值 —— **不**当消失处理，状态原样留着
        db.commit()
        return outcome

    states = _load_states(db, rule.id)

    for s in series:
        key = metrics_service.series_key(s.labels)
        value = float(s.value)  # 上面已经滤过 NaN
        st = states.get(key)
        if st is None:
            st = RuleMetricState(rule_id=rule.id, series_key=key)
            db.add(st)
            states[key] = st

        st.series_labels = json.dumps(s.labels or {}, ensure_ascii=False, default=str)
        st.last_value = value
        outcome.series_seen += 1

        if not compare(value, cfg.operator, cfg.threshold):
            if st.firing:
                outcome.recoveries.append(
                    _emit_recovery(db, rule, st, cfg, value, now, reason="回落")
                )
                outcome.recovered += 1
            st.breach_since = None
            st.firing = 0
            st.last_check_at = now
            continue

        outcome.breaching += 1
        stale = (
            st.last_check_at is not None
            and (now - st.last_check_at) > timedelta(seconds=GRACE_SECONDS)
        )
        # 首次成立、或断档后（且还没告警）重新计时。已在告警的不动计时 ——
        # 关掉一个正在响的告警比留着它更糟。
        if st.breach_since is None or (stale and not st.firing):
            st.breach_since = now

        breach_since = st.breach_since or now
        elapsed = (now - breach_since).total_seconds()
        if not st.firing and elapsed >= cfg.duration_seconds:
            st.firing = 1
            outcome.rows.append(build_metric_row(cfg, s.labels, key, value, breach_since=breach_since, now=now))
        elif st.firing:
            # 持续中：每分钟都产出一行，交给 rule_executor 的冷却去重压噪音。
            # 冷却窗口里重复只抬 event_count 不推 TG，窗口外算「又一次事件」——
            # 和 ES 规则行为一致。
            outcome.rows.append(build_metric_row(cfg, s.labels, key, value, breach_since=breach_since, now=now))
        st.last_check_at = now

    outcome.recovered += _gc_vanished(db, rule, seen, cfg, now, outcome)
    db.commit()
    return outcome


def _gc_vanished(db, rule, seen: set, cfg: MetricConfig, now: datetime, outcome) -> int:
    """上一轮有、这一轮没返回的 series：在告警的关掉并说清是数据中断。

    「关不掉的告警比关早了更糟」——exporter 挂了以后那条告警永远不会自己消失，
    只能在这里收尾。文案说实话（是中断不是真恢复）。
    没告警就消失的只删状态、不发任何通知（本来也没什么要撤回的）。
    """
    from app.models.metric_rule_state import RuleMetricState

    recovered = 0
    stale_rows = (
        db.query(RuleMetricState)
        .filter(RuleMetricState.rule_id == rule.id)
        .all()
    )
    for st in stale_rows:
        if st.series_key in seen:
            continue
        try:
            labels = json.loads(st.series_labels or "{}")
        except Exception:
            labels = {}
        value = st.last_value
        if st.firing:
            outcome.recoveries.append(
                _emit_recovery(db, rule, st, cfg, value, now, reason="数据中断")
            )
            recovered += 1
        db.delete(st)
    return recovered


# ── 恢复通知 ──────────────────────────────────────────────────────


def _emit_recovery(db, rule, st, cfg: MetricConfig, value, now: datetime, *, reason: str) -> Dict[str, Any]:
    """关掉对应告警 + 推一条「已恢复」。返回一行记账用的结果。

    **不走 `process_actions`** —— 那条路是「又命中了」的路，恢复是它的反面：
    要的是把已经开的告警关掉，不是再开一条。
    """
    from app.models.alert import Alert

    try:
        labels = json.loads(st.series_labels or "{}")
    except Exception:
        labels = {}
    identity = identity_of(labels, st.series_key)
    key = st.series_key

    # 找到这次持续期开的那条告警。指纹是 sha1(rule_id|src_ip|title)，
    # title 默认是「告警: {rule_name}」，所以按 rule + src_ip 找最稳妥。
    alert = (
        db.query(Alert)
        .filter(
            Alert.rule_id == rule.id,
            Alert.src_ip == identity,
            Alert.status.in_(("pending", "confirmed")),
        )
        .order_by(Alert.id.desc())
        .first()
    )
    if alert is not None:
        # `auto_resolved` 不等于 `resolved`：后者读起来是「人处理完了」，这里是
        # 指标自己回落、系统关的单。表里没有 resolved_by，全靠状态区分是谁关的。
        alert.status = "auto_resolved"
        alert.resolved_at = now

    text = _recovery_message(rule, cfg, labels, identity, value, st, now, reason=reason, alert_id=alert.id if alert else None)
    _push_recovery_telegram(rule, text)

    return {
        "src_ip": identity,
        "instance": labels.get("instance", ""),
        "series": series_signature(labels),
        "labels": labels,
        "promql": cfg.promql,
        "operator": cfg.operator,
        "threshold": cfg.threshold,
        "value": value,
        "recovery": True,
        "recovery_reason": reason,
        "closed_alert_id": alert.id if alert else None,
        "count": 1,
        "source": "metric_rule",
    }


def _recovery_message(rule, cfg, labels, identity, value, st, now: datetime, *, reason: str, alert_id=None) -> str:
    title_suffix = "已恢复（数据中断）" if reason == "数据中断" else "已恢复"
    value_text = "无观测" if value is None else f"{value}"
    lines = [
        f"🟢 {title_suffix} | {rule.name}",
        f"来源: {identity}",
        f"指标: {cfg.promql}",
    ]
    if reason == "数据中断":
        lines.append(f"该 series 已从查询结果中消失（exporter 挂了 / 实例下线），告警已关闭。")
        if st.breach_since:
            lines.append(f"首次超阈值: {st.breach_since.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        lines.append(f"当前值: {value_text}（阈值 {cfg.operator} {cfg.threshold}）")
        if st.breach_since:
            mins = int((now - st.breach_since).total_seconds() // 60)
            lines.append(f"本次持续: {mins} 分钟")
    if alert_id:
        lines.append(f"告警单号: #{alert_id}")
    lines.append(f"时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def _push_recovery_telegram(rule, text: str) -> None:
    """把恢复消息推到这条规则配置的每一个 Telegram 通道。失败只记日志。"""
    try:
        actions = json.loads(rule.actions or "[]") if rule.actions else []
    except Exception:
        actions = []
    tg_actions = [a for a in actions if isinstance(a, dict) and a.get("type") == "telegram"]
    if not tg_actions:
        return
    try:
        from app.services.telegram_notify import send_telegram
    except ImportError as exc:
        print(f"[MetricRule] Telegram push unavailable: {exc}")
        return

    for act in tg_actions:
        bot_token = (act.get("bot_token") or "").strip()
        chat_id = str(act.get("chat_id") or "").strip()
        if not bot_token or not chat_id:
            continue
        ok, err = send_telegram(bot_token, chat_id, text)
        if not ok:
            print(f"[MetricRule] recovery push failed: {err}")


# ── 只读预览 ──────────────────────────────────────────────────────


def preview_metric_rule(db, rule) -> Dict[str, Any]:
    """只看当前值，**不推进任何计时**。

    「测试 / 预览」按钮必须是只读的 —— 点一下就把 streak 往前推，会让用户
    在正式跑之前莫名其妙提前触发。
    """
    from app.services import metrics_service

    cfg = MetricConfig.from_rule(rule)
    if not cfg.promql.strip():
        return {"total": 0, "preview": [], "no_data": True, "error": "PromQL 表达式为空"}

    resp = metrics_service.query_instant(db, cfg.promql)
    if not resp.ok:
        return {"total": 0, "preview": [], "no_data": True, "error": resp.error or "查询失败"}

    states = _load_states(db, rule.id)
    preview: List[Dict[str, Any]] = []
    for s in resp.series:
        if not metrics_service.is_usable(s.value):
            continue
        key = metrics_service.series_key(s.labels)
        value = float(s.value)
        st = states.get(key)
        breaching = compare(value, cfg.operator, cfg.threshold)
        elapsed = 0
        if st is not None and st.breach_since is not None:
            elapsed = int((local_now() - st.breach_since).total_seconds())
        preview.append({
            "identity": identity_of(s.labels, key),
            "series": series_signature(s.labels),
            "value": value,
            "breaching": breaching,
            "firing": bool(st.firing) if st is not None else False,
            "sustained_seconds": elapsed,
            "need_seconds": cfg.duration_seconds,
        })

    return {
        "total": len(preview),
        "preview": preview[:50],
        "no_data": False,
        "error": None,
        "promql": cfg.promql,
        "operator": cfg.operator,
        "threshold": cfg.threshold,
        "duration_seconds": cfg.duration_seconds,
    }
