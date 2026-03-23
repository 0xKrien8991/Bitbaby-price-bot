"""Internationalization support for Chinese/English bilingual bot."""

TEXTS: dict[str, dict[str, str]] = {
    # Price display
    "price_title": {
        "en": "💰 {name} ({symbol})",
        "zh": "💰 {name} ({symbol})",
    },
    "price_usd": {
        "en": "Price: ${price}",
        "zh": "价格: ${price}",
    },
    "market_cap": {
        "en": "Market Cap: ${market_cap}",
        "zh": "市值: ${market_cap}",
    },
    "volume_24h": {
        "en": "24h Volume: ${volume}",
        "zh": "24h 成交量: ${volume}",
    },
    "change_24h": {
        "en": "24h Change: {change}%",
        "zh": "24h 涨跌幅: {change}%",
    },
    "change_7d": {
        "en": "7d Change: {change}%",
        "zh": "7d 涨跌幅: {change}%",
    },
    "high_low_24h": {
        "en": "24h High/Low: ${high} / ${low}",
        "zh": "24h 最高/最低: ${high} / ${low}",
    },
    "rank": {
        "en": "Rank: #{rank}",
        "zh": "排名: #{rank}",
    },
    # Buttons
    "btn_trade": {
        "en": "🚀 Trade on BitBaby",
        "zh": "🚀 去 BitBaby 交易",
    },
    "btn_lang_switch": {
        "en": "🌐 中文",
        "zh": "🌐 English",
    },
    # Messages
    "not_found": {
        "en": "❌ Token \"{symbol}\" not found. Please check the symbol and try again.",
        "zh": "❌ 未找到代币 \"{symbol}\"，请检查代币符号后重试。",
    },
    "help": {
        "en": (
            "📖 *BitBaby Price Bot*\n\n"
            "Query crypto prices with these commands:\n\n"
            "• `/p <symbol>` — Query token price\n"
            "• `/price <symbol>` — Query token price\n"
            "• `$<symbol>` — Quick query (e.g. `$BTC`)\n\n"
            "Examples: `/p btc`, `/price eth`, `$sol`\n\n"
            "Click the 🌐 button below any message to switch language."
        ),
        "zh": (
            "📖 *BitBaby 报价机器人*\n\n"
            "使用以下指令查询代币价格：\n\n"
            "• `/p <代币>` — 查询代币价格\n"
            "• `/price <代币>` — 查询代币价格\n"
            "• `$<代币>` — 快捷查询（如 `$BTC`）\n\n"
            "示例：`/p btc`、`/price eth`、`$sol`\n\n"
            "点击消息下方的 🌐 按钮切换语言。"
        ),
    },
    "welcome": {
        "en": (
            "👋 *Welcome to BitBaby Price Bot!*\n\n"
            "I can help you check real-time crypto prices.\n"
            "Use `/help` to see all commands.\n\n"
            "Try: `/p btc` or `$eth`"
        ),
        "zh": (
            "👋 *欢迎使用 BitBaby 报价机器人！*\n\n"
            "我可以帮你查询实时加密货币价格。\n"
            "使用 `/help` 查看所有指令。\n\n"
            "试试：`/p btc` 或 `$eth`"
        ),
    },
    "lang_switched": {
        "en": "✅ Language switched to English",
        "zh": "✅ 语言已切换为中文",
    },
    "fetching": {
        "en": "⏳ Fetching {symbol} price...",
        "zh": "⏳ 正在查询 {symbol} 价格...",
    },
    "error": {
        "en": "⚠️ Failed to fetch price data. Please try again later.",
        "zh": "⚠️ 获取价格数据失败，请稍后重试。",
    },
}


def t(key: str, lang: str = "en", **kwargs: object) -> str:
    """Get translated text by key and language."""
    entry = TEXTS.get(key, {})
    text = entry.get(lang, entry.get("en", f"[missing: {key}]"))
    if kwargs:
        text = text.format(**kwargs)
    return text


def format_number(value: float | None) -> str:
    """Format large numbers with appropriate suffixes."""
    if value is None:
        return "N/A"
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.2f}K"
    if value >= 1:
        return f"{value:.2f}"
    # Small decimals (meme coins etc.)
    return f"{value:.8f}"


def format_change(value: float | None) -> str:
    """Format price change percentage with arrow indicator."""
    if value is None:
        return "N/A"
    arrow = "📈" if value >= 0 else "📉"
    return f"{arrow} {value:+.2f}"


def build_price_message(data: dict, lang: str = "en") -> str:
    """Build formatted price message from coin data."""
    lines = [t("price_title", lang, name=data["name"], symbol=data["symbol"])]
    lines.append("━" * 24)

    if data.get("rank"):
        lines.append(t("rank", lang, rank=data["rank"]))

    lines.append(t("price_usd", lang, price=format_number(data["price_usd"])))

    if data.get("change_24h") is not None:
        lines.append(t("change_24h", lang, change=format_change(data["change_24h"])))

    if data.get("change_7d") is not None:
        lines.append(t("change_7d", lang, change=format_change(data["change_7d"])))

    if data.get("high_24h") is not None and data.get("low_24h") is not None:
        lines.append(
            t(
                "high_low_24h",
                lang,
                high=format_number(data["high_24h"]),
                low=format_number(data["low_24h"]),
            )
        )

    if data.get("volume_24h") is not None:
        lines.append(t("volume_24h", lang, volume=format_number(data["volume_24h"])))

    if data.get("market_cap") is not None:
        lines.append(t("market_cap", lang, market_cap=format_number(data["market_cap"])))

    return "\n".join(lines)
