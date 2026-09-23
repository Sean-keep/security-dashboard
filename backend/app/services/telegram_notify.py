"""
Telegram 告警推送（Bot API sendMessage）。

只出站：URL 固定为 api.telegram.org，目标由 bot token + chat_id 决定，
不接受用户自填 URL，因此不是 SSRF 面（对比「自定义 webhook」那种设计）。

推送失败绝不能中断规则执行：走到这里时告警已经落库、地址表也已写完，
Telegram 抖动不应该被记成规则失败。
"""
import httpx

# Telegram sendMessage 单条上限 4096 字符，超出会被 400 拒绝。
TELEGRAM_MESSAGE_LIMIT = 4000
# 单次规则执行最多推送条数。命中几百条时刷屏既没用也会触发 TG 限流。
TELEGRAM_MAX_MESSAGES_PER_RUN = 20
TELEGRAM_TIMEOUT_SECONDS = 10.0

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

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        # 网络层失败：超时、DNS、连接被拒等。不暴露 bot token。
        return False, f"请求 Telegram 失败: {exc.__class__.__name__}"

    try:
        data = resp.json()
    except ValueError:
        return False, f"Telegram 返回非 JSON（HTTP {resp.status_code}）"

    if resp.status_code == 200 and data.get("ok"):
        return True, ""

    # Telegram 业务错误统一 200+ok:false 或 4xx，描述在 description 字段。
    desc = data.get("description") if isinstance(data, dict) else None
    return False, desc or f"Telegram 返回 HTTP {resp.status_code}"
