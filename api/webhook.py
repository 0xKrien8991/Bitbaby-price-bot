"""
Vercel Serverless Function — Telegram Bot Webhook Handler.

Features:
- CoinGecko price queries (/p, /price, $SYMBOL)
- Multi-token query (/p btc eth sol)
- Trending tokens (/trending)
- Inline query mode (@bot btc)
- Chinese/English language switch
- Dynamic button management via admin commands
- Upstash Redis for persistent storage (buttons + language prefs)
"""

import asyncio
import json
import os
import re
from http.server import BaseHTTPRequestHandler

import aiohttp

# ─── Config ───────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en")
# Comma-separated Telegram user IDs who can manage buttons
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Upstash Redis REST API
UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Redis keys
REDIS_BUTTONS_KEY = "bitbaby:buttons"
REDIS_LANG_PREFIX = "bitbaby:lang:"

# ─── CoinGecko Symbol Mapping ────────────────────────────────────

SYMBOL_TO_ID: dict[str, str] = {
    "btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "usdc": "usd-coin",
    "bnb": "binancecoin", "xrp": "ripple", "ada": "cardano", "doge": "dogecoin",
    "sol": "solana", "dot": "polkadot", "matic": "matic-network", "pol": "matic-network",
    "shib": "shiba-inu", "trx": "tron", "avax": "avalanche-2", "link": "chainlink",
    "uni": "uniswap", "atom": "cosmos", "ltc": "litecoin", "etc": "ethereum-classic",
    "xlm": "stellar", "algo": "algorand", "near": "near", "ftm": "fantom",
    "apt": "aptos", "arb": "arbitrum", "op": "optimism", "sui": "sui",
    "sei": "sei-network", "inj": "injective-protocol", "ton": "the-open-network",
    "pepe": "pepe", "wif": "dogwifcoin", "bonk": "bonk", "floki": "floki",
    "fet": "fetch-ai", "rndr": "render-token", "grt": "the-graph", "fil": "filecoin",
    "aave": "aave", "mkr": "maker", "crv": "curve-dao-token", "ldo": "lido-dao",
    "sand": "the-sandbox", "mana": "decentraland", "axs": "axie-infinity",
    "imx": "immutable-x", "ape": "apecoin", "cake": "pancakeswap-token",
    "sushi": "sushi", "1inch": "1inch", "snx": "havven", "comp": "compound-governance-token",
    "yfi": "yearn-finance", "ens": "ethereum-name-service", "vet": "vechain",
    "hbar": "hedera-hashgraph", "icp": "internet-computer", "theta": "theta-token",
    "neo": "neo", "eos": "eos", "xtz": "tezos", "flow": "flow", "rose": "oasis-network",
    "kava": "kava", "celo": "celo", "mina": "mina-protocol", "kas": "kaspa",
    "cfx": "conflux-token", "stx": "blockstack", "bch": "bitcoin-cash",
    "okb": "okb", "cro": "crypto-com-chain", "wbtc": "wrapped-bitcoin", "dai": "dai",
}

# ─── i18n ─────────────────────────────────────────────────────────

TEXTS = {
    "price_title":     {"en": "💰 {name} ({symbol})", "zh": "💰 {name} ({symbol})"},
    "price_usd":       {"en": "Price: ${price}", "zh": "价格: ${price}"},
    "market_cap":      {"en": "Market Cap: ${market_cap}", "zh": "市值: ${market_cap}"},
    "volume_24h":      {"en": "24h Volume: ${volume}", "zh": "24h 成交量: ${volume}"},
    "change_24h":      {"en": "24h Change: {change}%", "zh": "24h 涨跌幅: {change}%"},
    "change_7d":       {"en": "7d Change: {change}%", "zh": "7d 涨跌幅: {change}%"},
    "high_low_24h":    {"en": "24h High/Low: ${high} / ${low}", "zh": "24h 最高/最低: ${high} / ${low}"},
    "rank":            {"en": "Rank: #{rank}", "zh": "排名: #{rank}"},
    "btn_lang_switch": {"en": "🌐 中文", "zh": "🌐 English"},
    "not_found": {
        "en": '❌ Token "{symbol}" not found. Please check the symbol and try again.',
        "zh": '❌ 未找到代币 "{symbol}"，请检查代币符号后重试。',
    },
    "help": {
        "en": (
            "📖 BitBaby Price Bot\n\n"
            "• /p <symbol> — Query price\n"
            "• /p btc eth sol — Multi query\n"
            "• $BTC — Quick query\n"
            "• /trending — Trending coins\n"
            "• /lang en|zh — Switch language\n\n"
            "Also works in inline mode:\n"
            "Type @botname btc in any chat.\n\n"
            "Click 🌐 to switch language."
        ),
        "zh": (
            "📖 BitBaby 报价机器人\n\n"
            "• /p <代币> — 查询价格\n"
            "• /p btc eth sol — 多币种查询\n"
            "• $BTC — 快捷查询\n"
            "• /trending — 热门代币\n"
            "• /lang en|zh — 切换语言\n\n"
            "也支持内联模式：\n"
            "在任意聊天框输入 @机器人用户名 btc\n\n"
            "点击 🌐 切换语言。"
        ),
    },
    "admin_help": {
        "en": (
            "🔧 Admin Commands:\n\n"
            "• /addbutton <text> | <url>\n"
            "  Add a button below price messages\n\n"
            "• /editbutton <number> <text> | <url>\n"
            "  Edit an existing button\n\n"
            "• /removebutton <number>\n"
            "  Remove a button by its number\n\n"
            "• /listbuttons\n"
            "  Show all current buttons\n\n"
            "• /clearbuttons\n"
            "  Remove all buttons\n\n"
            "Example:\n"
            "/addbutton 🚀 Trade on BitBaby | https://www.bitbaby.com/en-us"
        ),
        "zh": (
            "🔧 管理员指令：\n\n"
            "• /addbutton <文字> | <链接>\n"
            "  添加价格消息下方的按钮\n\n"
            "• /editbutton <编号> <文字> | <链接>\n"
            "  修改已有按钮\n\n"
            "• /removebutton <编号>\n"
            "  按编号删除按钮\n\n"
            "• /listbuttons\n"
            "  查看所有按钮\n\n"
            "• /clearbuttons\n"
            "  清空所有按钮\n\n"
            "示例：\n"
            "/addbutton 🚀 去 BitBaby 交易 | https://www.bitbaby.com/en-us"
        ),
    },
    "welcome": {
        "en": "👋 Welcome to BitBaby Price Bot!\n\nUse /help to see commands.\nTry: /p btc or $eth",
        "zh": "👋 欢迎使用 BitBaby 报价机器人！\n\n使用 /help 查看指令。\n试试：/p btc 或 $eth",
    },
    "lang_switched":   {"en": "✅ Language switched to English", "zh": "✅ 语言已切换为中文"},
    "error":           {"en": "⚠️ Failed to fetch price. Please try again later.", "zh": "⚠️ 获取价格失败，请稍后重试。"},
    "no_permission":   {"en": "🚫 Admin only.", "zh": "🚫 仅管理员可用。"},
    "btn_added":       {"en": "✅ Button added: {text}", "zh": "✅ 按钮已添加：{text}"},
    "btn_edited":      {"en": "✅ Button #{num} updated: {text}", "zh": "✅ 按钮 #{num} 已更新：{text}"},
    "btn_removed":     {"en": "✅ Button #{num} removed.", "zh": "✅ 按钮 #{num} 已删除。"},
    "btn_cleared":     {"en": "✅ All buttons cleared.", "zh": "✅ 所有按钮已清空。"},
    "btn_list_empty":  {"en": "📋 No buttons configured yet.\nUse /addbutton to add one.", "zh": "📋 还没有配置按钮。\n使用 /addbutton 添加。"},
    "btn_invalid_fmt": {"en": "❌ Format: /addbutton Button Text | https://url", "zh": "❌ 格式：/addbutton 按钮文字 | https://链接"},
    "btn_invalid_num": {"en": "❌ Invalid button number.", "zh": "❌ 无效的按钮编号。"},
    "trending_title":  {"en": "🔥 Trending Coins", "zh": "🔥 热门代币"},
    "trending_empty":  {"en": "No trending data available.", "zh": "暂无热门数据。"},
    "multi_query_max": {"en": "⚠️ Max 5 tokens per query.", "zh": "⚠️ 每次最多查询 5 个代币。"},
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    entry = TEXTS.get(key, {})
    text = entry.get(lang, entry.get("en", f"[{key}]"))
    if kwargs:
        text = text.format(**kwargs)
    return text


# ─── Upstash Redis Helpers ───────────────────────────────────────

async def redis_get(key: str) -> str | None:
    """GET a value from Upstash Redis."""
    if not UPSTASH_URL:
        return None
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{UPSTASH_URL}/get/{key}", headers=headers) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data.get("result")


async def redis_set(key: str, value: str) -> bool:
    """SET a value in Upstash Redis."""
    if not UPSTASH_URL:
        return False
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{UPSTASH_URL}", headers=headers,
                          json=["SET", key, value]) as r:
            return r.status == 200


async def redis_del(key: str) -> bool:
    """DEL a key from Upstash Redis."""
    if not UPSTASH_URL:
        return False
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{UPSTASH_URL}", headers=headers,
                          json=["DEL", key]) as r:
            return r.status == 200


# ─── Button Storage ──────────────────────────────────────────────
# Buttons stored as JSON array: [{"text": "Trade", "url": "https://..."}, ...]

async def get_buttons() -> list[dict]:
    """Get all configured buttons from Redis."""
    raw = await redis_get(REDIS_BUTTONS_KEY)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


async def save_buttons(buttons: list[dict]) -> bool:
    """Save buttons to Redis."""
    return await redis_set(REDIS_BUTTONS_KEY, json.dumps(buttons))


# ─── Language Storage ────────────────────────────────────────────

async def get_lang(chat_id: int) -> str:
    """Get language preference for a chat from Redis."""
    result = await redis_get(f"{REDIS_LANG_PREFIX}{chat_id}")
    return result if result in ("en", "zh") else DEFAULT_LANG


async def set_lang(chat_id: int, lang: str) -> None:
    """Save language preference for a chat to Redis."""
    await redis_set(f"{REDIS_LANG_PREFIX}{chat_id}", lang)


# ─── Formatters ──────────────────────────────────────────────────

def fmt_num(v) -> str:
    if v is None:
        return "N/A"
    if v >= 1_000_000_000_000:
        return f"{v/1e12:.2f}T"
    if v >= 1_000_000_000:
        return f"{v/1e9:.2f}B"
    if v >= 1_000_000:
        return f"{v/1e6:.2f}M"
    if v >= 1_000:
        return f"{v/1e3:.2f}K"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.8f}"


def fmt_change(v) -> str:
    if v is None:
        return "N/A"
    arrow = "📈" if v >= 0 else "📉"
    return f"{arrow} {v:+.2f}"


# ─── CoinGecko ───────────────────────────────────────────────────

async def search_coin_id(symbol: str) -> str | None:
    sym = symbol.lower().strip()
    if sym in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[sym]
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{COINGECKO_API}/search", params={"query": sym}) as r:
            if r.status != 200:
                return None
            data = await r.json()
            for c in data.get("coins", []):
                if c.get("symbol", "").lower() == sym:
                    return c["id"]
            coins = data.get("coins", [])
            return coins[0]["id"] if coins else None


async def fetch_price(symbol: str) -> dict | None:
    coin_id = await search_coin_id(symbol)
    if not coin_id:
        return None
    params = {"localization": "false", "tickers": "false",
              "community_data": "false", "developer_data": "false", "sparkline": "false"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{COINGECKO_API}/coins/{coin_id}", params=params) as r:
            if r.status != 200:
                return None
            data = await r.json()
    m = data.get("market_data", {})
    return {
        "name": data.get("name", "Unknown"),
        "symbol": data.get("symbol", symbol).upper(),
        "price_usd": m.get("current_price", {}).get("usd"),
        "market_cap": m.get("market_cap", {}).get("usd"),
        "volume_24h": m.get("total_volume", {}).get("usd"),
        "change_24h": m.get("price_change_percentage_24h"),
        "change_7d": m.get("price_change_percentage_7d"),
        "high_24h": m.get("high_24h", {}).get("usd"),
        "low_24h": m.get("low_24h", {}).get("usd"),
        "rank": data.get("market_cap_rank"),
    }


async def fetch_trending() -> list[dict]:
    """Fetch trending coins from CoinGecko."""
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{COINGECKO_API}/search/trending") as r:
            if r.status != 200:
                return []
            data = await r.json()
    results = []
    for item in data.get("coins", [])[:10]:
        coin = item.get("item", {})
        results.append({
            "name": coin.get("name", ""),
            "symbol": coin.get("symbol", "").upper(),
            "rank": coin.get("market_cap_rank"),
            "price_btc": coin.get("price_btc", 0),
            "score": coin.get("score", 0),
        })
    return results


# ─── Message Builder ─────────────────────────────────────────────

def build_price_msg(data: dict, lang: str) -> str:
    lines = [t("price_title", lang, name=data["name"], symbol=data["symbol"])]
    lines.append("━" * 24)
    if data.get("rank"):
        lines.append(t("rank", lang, rank=data["rank"]))
    lines.append(t("price_usd", lang, price=fmt_num(data["price_usd"])))
    if data.get("change_24h") is not None:
        lines.append(t("change_24h", lang, change=fmt_change(data["change_24h"])))
    if data.get("change_7d") is not None:
        lines.append(t("change_7d", lang, change=fmt_change(data["change_7d"])))
    if data.get("high_24h") is not None and data.get("low_24h") is not None:
        lines.append(t("high_low_24h", lang, high=fmt_num(data["high_24h"]), low=fmt_num(data["low_24h"])))
    if data.get("volume_24h") is not None:
        lines.append(t("volume_24h", lang, volume=fmt_num(data["volume_24h"])))
    if data.get("market_cap") is not None:
        lines.append(t("market_cap", lang, market_cap=fmt_num(data["market_cap"])))
    return "\n".join(lines)


# ─── Keyboard Builders ──────────────────────────────────────────

async def price_keyboard(symbol: str, lang: str) -> dict:
    """Build keyboard with dynamic buttons + language switch."""
    buttons = await get_buttons()
    keyboard = []

    # Custom buttons from Redis (one per row)
    for btn in buttons:
        keyboard.append([{"text": btn["text"], "url": btn["url"]}])

    # Language switch button (always last row)
    target_lang = "zh" if lang == "en" else "en"
    keyboard.append([{
        "text": t("btn_lang_switch", lang),
        "callback_data": f"lang:{target_lang}:{symbol}",
    }])

    return {"inline_keyboard": keyboard}


def simple_keyboard(lang: str, msg_type: str = "help") -> dict:
    target_lang = "zh" if lang == "en" else "en"
    return {
        "inline_keyboard": [[{
            "text": t("btn_lang_switch", lang),
            "callback_data": f"slang:{target_lang}:{msg_type}",
        }]]
    }


# ─── Telegram API Helpers ────────────────────────────────────────

async def tg_send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with aiohttp.ClientSession() as s:
        await s.post(f"{TELEGRAM_API}/sendMessage", data=payload)


async def tg_edit(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with aiohttp.ClientSession() as s:
        await s.post(f"{TELEGRAM_API}/editMessageText", data=payload)


async def tg_answer_callback(callback_query_id):
    async with aiohttp.ClientSession() as s:
        await s.post(f"{TELEGRAM_API}/answerCallbackQuery",
                     data={"callback_query_id": callback_query_id})


# ─── Admin Command Helpers ───────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def parse_button_input(text: str) -> tuple[str, str] | None:
    """Parse 'Button Text | https://url' format. Returns (text, url) or None."""
    if "|" not in text:
        return None
    parts = text.split("|", 1)
    btn_text = parts[0].strip()
    btn_url = parts[1].strip()
    if not btn_text or not btn_url:
        return None
    return (btn_text, btn_url)


# ─── Bot Logic ───────────────────────────────────────────────────

async def handle_message(msg: dict):
    """Process an incoming message."""
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id", 0)
    text = msg.get("text", "").strip()
    lang = await get_lang(chat_id)

    # ── General Commands ──

    if text.startswith("/start"):
        await tg_send(chat_id, t("welcome", lang), simple_keyboard(lang, "welcome"))
        return

    if text.startswith("/help"):
        help_text = t("help", lang)
        if is_admin(user_id):
            help_text += "\n\n" + t("admin_help", lang)
        await tg_send(chat_id, help_text, simple_keyboard(lang, "help"))
        return

    if text.startswith("/lang"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].lower() in ("en", "zh"):
            new_lang = parts[1].lower()
            await set_lang(chat_id, new_lang)
            await tg_send(chat_id, t("lang_switched", new_lang), simple_keyboard(new_lang, "help"))
        else:
            await tg_send(chat_id, "Usage: /lang en | /lang zh")
        return

    # ── Admin: Button Management ──

    if text.startswith("/addbutton"):
        if not is_admin(user_id):
            await tg_send(chat_id, t("no_permission", lang))
            return
        content = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        parsed = parse_button_input(content)
        if not parsed:
            await tg_send(chat_id, t("btn_invalid_fmt", lang))
            return
        btn_text, btn_url = parsed
        buttons = await get_buttons()
        buttons.append({"text": btn_text, "url": btn_url})
        await save_buttons(buttons)
        await tg_send(chat_id, t("btn_added", lang, text=btn_text))
        return

    if text.startswith("/editbutton"):
        if not is_admin(user_id):
            await tg_send(chat_id, t("no_permission", lang))
            return
        # Format: /editbutton 1 New Text | https://new-url
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await tg_send(chat_id, "Usage: /editbutton <number> <text> | <url>")
            return
        try:
            idx = int(parts[1]) - 1
        except ValueError:
            await tg_send(chat_id, t("btn_invalid_num", lang))
            return
        parsed = parse_button_input(parts[2])
        if not parsed:
            await tg_send(chat_id, t("btn_invalid_fmt", lang))
            return
        buttons = await get_buttons()
        if idx < 0 or idx >= len(buttons):
            await tg_send(chat_id, t("btn_invalid_num", lang))
            return
        btn_text, btn_url = parsed
        buttons[idx] = {"text": btn_text, "url": btn_url}
        await save_buttons(buttons)
        await tg_send(chat_id, t("btn_edited", lang, num=idx + 1, text=btn_text))
        return

    if text.startswith("/removebutton"):
        if not is_admin(user_id):
            await tg_send(chat_id, t("no_permission", lang))
            return
        parts = text.split()
        if len(parts) < 2:
            await tg_send(chat_id, "Usage: /removebutton <number>")
            return
        try:
            idx = int(parts[1]) - 1
        except ValueError:
            await tg_send(chat_id, t("btn_invalid_num", lang))
            return
        buttons = await get_buttons()
        if idx < 0 or idx >= len(buttons):
            await tg_send(chat_id, t("btn_invalid_num", lang))
            return
        buttons.pop(idx)
        await save_buttons(buttons)
        await tg_send(chat_id, t("btn_removed", lang, num=idx + 1))
        return

    if text.startswith("/listbuttons"):
        if not is_admin(user_id):
            await tg_send(chat_id, t("no_permission", lang))
            return
        buttons = await get_buttons()
        if not buttons:
            await tg_send(chat_id, t("btn_list_empty", lang))
            return
        lines = ["📋 Current Buttons:" if lang == "en" else "📋 当前按钮：", ""]
        for i, btn in enumerate(buttons, 1):
            lines.append(f"{i}. {btn['text']}\n   → {btn['url']}")
        await tg_send(chat_id, "\n".join(lines))
        return

    if text.startswith("/clearbuttons"):
        if not is_admin(user_id):
            await tg_send(chat_id, t("no_permission", lang))
            return
        await redis_del(REDIS_BUTTONS_KEY)
        await tg_send(chat_id, t("btn_cleared", lang))
        return

    # ── Trending ──

    if text.startswith("/trending"):
        await handle_trending(chat_id, lang)
        return

    # ── Price Queries (multi-token support) ──

    if text.startswith("/p ") or text.startswith("/price "):
        parts = text.split()
        symbols = [s.upper() for s in parts[1:] if s and not s.startswith("/")]
        if not symbols:
            await tg_send(chat_id, t("help", lang), simple_keyboard(lang, "help"))
            return
        if len(symbols) > 5:
            await tg_send(chat_id, t("multi_query_max", lang))
            symbols = symbols[:5]
        for symbol in symbols:
            await query_and_reply(chat_id, symbol, lang)
        return

    # /p@botname <symbol> (group commands with bot username)
    if text.startswith("/p@") or text.startswith("/price@"):
        parts = text.split()
        symbols = [s.upper() for s in parts[1:] if s]
        for symbol in symbols[:5]:
            await query_and_reply(chat_id, symbol, lang)
        return

    # $BTC style (supports multiple: $BTC $ETH)
    matches = re.findall(r"\$([A-Za-z0-9]{1,10})", text)
    if matches:
        for symbol in [m.upper() for m in matches[:5]]:
            await query_and_reply(chat_id, symbol, lang)


async def handle_callback_query(cbq: dict):
    """Process an inline button click."""
    callback_id = cbq["id"]
    data = cbq.get("data", "")
    chat_id = cbq["message"]["chat"]["id"]
    message_id = cbq["message"]["message_id"]

    await tg_answer_callback(callback_id)

    # Price message language switch: lang:<target_lang>:<symbol>
    if data.startswith("lang:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            new_lang = parts[1]
            symbol = parts[2]
            await set_lang(chat_id, new_lang)

            price_data = await fetch_price(symbol)
            if price_data:
                text = build_price_msg(price_data, new_lang)
                kb = await price_keyboard(symbol, new_lang)
                await tg_edit(chat_id, message_id, text, kb)
            else:
                await tg_edit(chat_id, message_id,
                              t("not_found", new_lang, symbol=symbol),
                              simple_keyboard(new_lang))

    # Simple message language switch: slang:<target_lang>:<msg_type>
    elif data.startswith("slang:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            new_lang = parts[1]
            msg_type = parts[2]
            await set_lang(chat_id, new_lang)

            if msg_type == "welcome":
                text = t("welcome", new_lang)
            else:
                text = t("help", new_lang)
            await tg_edit(chat_id, message_id, text, simple_keyboard(new_lang, msg_type))


async def handle_trending(chat_id: int, lang: str):
    """Fetch and send trending coins."""
    try:
        coins = await fetch_trending()
    except Exception:
        await tg_send(chat_id, t("error", lang))
        return

    if not coins:
        await tg_send(chat_id, t("trending_empty", lang))
        return

    lines = [t("trending_title", lang), "━" * 24]
    for i, coin in enumerate(coins, 1):
        rank_str = f"#{coin['rank']}" if coin.get("rank") else "—"
        lines.append(f"{i}. {coin['name']} ({coin['symbol']})  [{rank_str}]")

    # Add tip to query
    if lang == "zh":
        lines.append("\n💡 输入 /p <代币> 查看详情")
    else:
        lines.append("\n💡 Use /p <symbol> for details")

    await tg_send(chat_id, "\n".join(lines), simple_keyboard(lang, "help"))


async def query_and_reply(chat_id: int, symbol: str, lang: str):
    """Fetch price and send to chat."""
    try:
        price_data = await fetch_price(symbol)
    except Exception:
        await tg_send(chat_id, t("error", lang))
        return

    if not price_data:
        await tg_send(chat_id, t("not_found", lang, symbol=symbol), simple_keyboard(lang))
        return

    text = build_price_msg(price_data, lang)
    kb = await price_keyboard(symbol, lang)
    await tg_send(chat_id, text, kb)


async def handle_inline_query(inline_query: dict):
    """Handle inline mode: user types @botname btc in any chat."""
    query_id = inline_query["id"]
    query_text = inline_query.get("query", "").strip()

    if not query_text or len(query_text) < 1:
        # Return empty result
        await tg_answer_inline(query_id, [])
        return

    # Try to fetch price for the query
    try:
        price_data = await fetch_price(query_text)
    except Exception:
        await tg_answer_inline(query_id, [])
        return

    if not price_data:
        await tg_answer_inline(query_id, [])
        return

    # Build result
    lang = DEFAULT_LANG
    msg_text = build_price_msg(price_data, lang)
    buttons = await get_buttons()
    keyboard = []
    for btn in buttons:
        keyboard.append([{"text": btn["text"], "url": btn["url"]}])

    result = {
        "type": "article",
        "id": f"price_{price_data['symbol']}",
        "title": f"{price_data['name']} ({price_data['symbol']})",
        "description": f"${fmt_num(price_data['price_usd'])}  {fmt_change(price_data.get('change_24h'))}%",
        "input_message_content": {"message_text": msg_text},
    }
    if keyboard:
        result["reply_markup"] = {"inline_keyboard": keyboard}

    await tg_answer_inline(query_id, [result])


async def tg_answer_inline(inline_query_id: str, results: list):
    """Answer an inline query."""
    payload = {
        "inline_query_id": inline_query_id,
        "results": json.dumps(results),
        "cache_time": 30,
    }
    async with aiohttp.ClientSession() as s:
        await s.post(f"{TELEGRAM_API}/answerInlineQuery", data=payload)


# ─── Vercel Handler ──────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function entry point."""

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            update = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        if "message" in update:
            asyncio.run(handle_message(update["message"]))
        elif "callback_query" in update:
            asyncio.run(handle_callback_query(update["callback_query"]))
        elif "inline_query" in update:
            asyncio.run(handle_inline_query(update["inline_query"]))

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        """Health check."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "BitBaby Price Bot is running"}')
