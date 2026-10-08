"""
Telegram 告警推送（Bot API sendMessage）。

只出站：URL 固定为 api.telegram.org，目标由 bot token + chat_id 决定，
不接受用户自填 URL，因此不是 SSRF 面（对比「自定义 webhook」那种设计）。
**这个 host 就是安全边界，不要改成可配置。** 需要绕开网络限制时配出站代理
（`TELEGRAM_PROXY` / `HTTPS_PROXY`），代理是运维自己起的跳板，不是用户输入。

推送失败绝不能中断规则执行：走到这里时告警已经落库、地址表也已写完，
Telegram 抖动不应该被记成规则失败。

网络错误要报「卡在哪一层」：只吐 `ConnectError` 这种类名，运维分不清是
DNS 污染、TCP 被拒、TLS 被 RST，还是 token 填错 —— 后者根本不是网络问题。
"""
import os
import socket
import ssl
import time

import httpx

# Telegram sendMessage 单条上限 4096 字符，超出会被 400 拒绝。
TELEGRAM_MESSAGE_LIMIT = 4000
# 单次规则执行最多推送条数。命中几百条时刷屏既没用也会触发 TG 限流。
TELEGRAM_MAX_MESSAGES_PER_RUN = 20
TELEGRAM_TIMEOUT_SECONDS = 10.0

# 出站目标。见模块头：固定，不可配置。
TELEGRAM_HOST = "api.telegram.org"
TELEGRAM_PORT = 443

# 失败后分层探测的单层超时。只在失败路径跑，但也别让一次测试卡住半分钟。
_PROBE_TIMEOUT = 2.0
# 探测是真网络开销。网络整体不通时规则一次要推 20 条、条条失败，
# 不该条条重探 —— 结果缓存 60 秒，网络恢复后自然过期重来。
_PROBE_TTL_SECONDS = 60.0
_PROBE_CACHE: dict[str, tuple[float, str]] = {}

_SEVERITY_PREFIX = {
    "critical": "🔴 严重",
    "high": "🟠 高危",
    "medium": "🟡 中危",
    "low": "🟢 低危",
}


def build_alert_message(title: str, content: str, severity: str = "medium",
                        src_ip: str = "", rule_name: str = "", created_at: str = "") -> str:
    """组装推送正文。与告警列表同一套文案，用户在 TG 里看到的就是告警本身。"""
    prefix = _SEVERITY_PREFIX.get(severity, "🟡 中危")
    lines = [f"{prefix} | {title or '规则告警'}"]
    if src_ip:
        lines.append(f"来源 IP: {src_ip}")
    if rule_name:
        lines.append(f"触发规则: {rule_name}")
    if content:
        lines.append("")
        lines.append(content)
    if created_at:
        lines.append("")
        lines.append(f"时间: {created_at}")
    return "\n".join(lines)


# ── 出站代理 ──────────────────────────────────────────────


def _proxy_url() -> str:
    """出站代理地址，空串表示直连。

    `TELEGRAM_PROXY` 优先于标准的 `HTTPS_PROXY` / `ALL_PROXY` —— 有的环境里
    走通用代理的流量和走 Telegram 跳板的不是同一条路。显式取出来传给 httpx，
    不依赖 `trust_env`，这样报错时说得清「用的到底是哪个代理」。
    """
    for key in (
        "TELEGRAM_PROXY",
        "HTTPS_PROXY", "https_proxy",
        "ALL_PROXY", "all_proxy",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def _proxy_hint() -> str:
    """按「配没配代理」给出对应的动作建议。"""
    if _proxy_url():
        return "已配置出站代理但仍然失败，请确认代理本身能访问 api.telegram.org"
    return (
        "若在受限网络，请配置出站代理后重试："
        "TELEGRAM_PROXY=socks5://127.0.0.1:1080 "
        "或 HTTPS_PROXY=http://127.0.0.1:7890"
    )


# ── 网络诊断 ──────────────────────────────────────────────


def _exception_chain(exc: BaseException, limit: int = 4) -> str:
    """展开 `__cause__` / `__context__` 链。

    httpx 的 `ConnectError` 的 `str()` 经常是空串，真正的信息在内层异常里
    （`ConnectTimeout`、`ssl.SSLError`、`socket.gaierror`…），只打印类名会把
    唯一有用的线索丢掉。
    """
    parts: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen and len(parts) < limit:
        seen.add(id(cur))
        msg = str(cur).strip()
        part = f"{type(cur).__name__}: {msg}" if msg else type(cur).__name__
        # httpx 层层包装时常出现连续两层同样的类+文案，重复一遍没信息量。
        if not parts or parts[-1] != part:
            parts.append(part)
        cur = cur.__cause__ or cur.__context__
    return " ← ".join(parts)


def _resolve(host: str, port: int) -> list[str]:
    """解析出不重复的 IP 列表。失败返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError:
        return []
    addrs: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in addrs:
            addrs.append(ip)
    return addrs


def _probe_network(host: str = TELEGRAM_HOST, port: int = TELEGRAM_PORT) -> str:
    """DNS → TCP → TLS 三层探测，指出卡在哪一层。任何异常都不外抛。

    只在请求失败后调用，成功路径零开销。DNS 污染、SNI 阻断这类问题
    光看 httpx 的异常类型判断不出来，得自己分层试一遍。
    """
    key = f"{host}:{port}"
    now = time.monotonic()
    cached = _PROBE_CACHE.get(key)
    if cached and now - cached[0] < _PROBE_TTL_SECONDS:
        return cached[1]
    text = _probe_network_uncached(host, port)
    _PROBE_CACHE[key] = (now, text)
    return text


def _probe_network_uncached(host: str, port: int) -> str:
    notes: list[str] = []

    addrs = _resolve(host, port)
    if not addrs:
        return f"DNS 解析失败：{host} 无解析结果"
    v4 = [a for a in addrs if ":" not in a]
    v6 = [a for a in addrs if ":" in a]
    shown = "、".join(addrs[:4]) + ("…" if len(addrs) > 4 else "")
    notes.append(f"DNS 解析到 {shown}")
    if addrs and not v4:
        notes.append("只有 IPv6 结果，通常是 DNS 污染或本地没有 IPv6 出口")

    # 优先连 IPv4 —— v6-only 的假结果连不上，会把诊断带偏
    target = (v4 or v6 or [host])[0]
    try:
        with socket.create_connection((target, port), timeout=_PROBE_TIMEOUT):
            pass
    except OSError as exc:
        notes.append(f"TCP 连接失败（{type(exc).__name__}: {exc}）")
        return "；".join(notes)
    notes.append("TCP 可连通")

    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((target, port), timeout=_PROBE_TIMEOUT) as raw:
            with ctx.wrap_socket(raw, server_hostname=host):
                notes.append("TLS 握手正常")
    except ssl.SSLError as exc:
        notes.append(
            f"TLS 握手失败（{type(exc).__name__}: {exc}）"
            "——常见于证书或 SNI 被中间设备改写"
        )
    except OSError as exc:
        if isinstance(exc, ConnectionResetError) or "reset" in str(exc).lower():
            notes.append(
                f"TLS 握手被对端重置（{target}:{port}）"
                "——典型 SNI 阻断：TCP 能连上但握手被打断，是网络屏蔽了 "
                f"{host}，不是 token 的问题"
            )
        else:
            notes.append(f"TLS 握手异常（{type(exc).__name__}: {exc}）")
    return "；".join(notes)


def _transport_error(exc: BaseException) -> str:
    """把网络层异常翻成运维能直接照做的一段话。绝不带出 bot token。"""
    segs = [f"请求 Telegram 失败: {_exception_chain(exc)}"]
    try:
        probe = _probe_network()
    except Exception:  # 探测自身出问题也不能把原始报错弄丢
        probe = ""
    if probe:
        segs.append(f"诊断: {probe}")
    segs.append(f"建议: {_proxy_hint()}")
    return "；".join(segs)


# ── 发送 ──────────────────────────────────────────────────


def send_telegram(bot_token: str, chat_id: str, text: str,
                  timeout: float = TELEGRAM_TIMEOUT_SECONDS):
    """发送一条 Telegram 消息。返回 (ok, err)。err 为空串表示成功。

    凭据缺失属于配置问题，直接返回错误而不是抛异常 —— 调用方（规则执行器）
    只应记日志，不应中断。
    """
    bot_token = (bot_token or "").strip()
    chat_id = (str(chat_id) if chat_id is not None else "").strip()
    text = (text or "").strip()

    if not bot_token:
        return False, "未配置 Telegram bot token"
    if not chat_id:
        return False, "未配置 Telegram chat_id"
    if not text:
        return False, "消息内容为空"

    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        text = text[:TELEGRAM_MESSAGE_LIMIT] + "\n…（内容过长已截断）"

    # URL 里带着 bot token —— 任何报错串都不要回显 url。
    url = f"https://{TELEGRAM_HOST}/bot{bot_token}/sendMessage"
    kwargs: dict = {
        "json": {"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        "timeout": timeout,
    }
    proxy = _proxy_url()
    if proxy:
        kwargs["proxy"] = proxy
    try:
        resp = httpx.post(url, **kwargs)
    except httpx.HTTPError as exc:
        # 网络层失败：超时、DNS、连接被拒、TLS 被 RST 等。
        return False, _transport_error(exc)

    try:
        data = resp.json()
    except ValueError:
        return False, f"Telegram 返回非 JSON（HTTP {resp.status_code}）"

    if resp.status_code == 200 and data.get("ok"):
        return True, ""

    # Telegram 业务错误统一 200+ok:false 或 4xx，描述在 description 字段。
    # 这类失败和网络无关，所以不附加网络诊断 —— 混在一起反而误导。
    desc = data.get("description") if isinstance(data, dict) else None
    return False, desc or f"Telegram 返回 HTTP {resp.status_code}"
