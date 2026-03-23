"""
Vercel Serverless Function — Telegram Bot Webhook Handler.

Telegram sends each message as an HTTP POST to this endpoint.
Vercel runs this function on-demand (no server needed).
"""

import json
import os
import re

import aiohttp
from http.server import BaseHTTPRequestHandler

# ─── Config ───────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TRADE_URL = os.getenv("TRADE_URL", "https://www.bitbaby.com/en-us")
TRADE_URL_MODE = os.getenv("TRADE_URL_MODE", "direct")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_API = "https://api.coingecko.com/api/v3"

# ─── CoinGecko Symbol Mapping (top tokens) ───────────────────────

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
    "ton": "the-open-network", "okb": "okb", "cro": "crypto-com-chain",
    "wbtc": "wrapped-bitcoin", "dai": "dai",
}

# ─── i18n ─────────────────────────────────────────────────────────

TEXTS = {
    "price_title":    {"en": "💰 {name} ({symbol})", "zh": "💰 {name} ({symbol})"},
    "price_usd":      {"en": "Price: ${price}", "zh": "价格: ${price}"},
    "market_cap":     {"en": "Market Cap: ${market_cap}", "zh": "市值: ${market_cap}"},
    "volume_24h":     {"en": "24h Volume: ${volume}", "zh": "24h 成交量: ${volume}"},
    "change_24h":     {"en": "24h Change: {change}%", "zh": "24h 涨跌幅: {change}%"},
    "change_7d":      {"en": "7d Change: {change}%", "zh": "7d 涨跌幅: {change}%"},
    "high_low_24h":   {"en": "24h High/Low: ${high} / ${low}", "zh": "24h 最高/最低: ${high} / ${low}"},
    "rank":           {"en": "Rank: #{rank}", "zh": "排名: #{rank}"},
    "btn_trade":      {"en": "🚀 Trade on BitBaby", "zh": "🚀 去 BitBaby 交易"},
    "btn_lang_switch": {"en": "🌐 中文", "zh": "🌐 English"},
    "not_found": {
        "en": '❌ Token "{symbol}" not found. Please check the symbol and try again.',
        "zh": '❌ 未找到代币 "{symbol}"，请检查代币符号后重试。',
    },
    "help": {
        "en": (
            "📖 BitBaby Price Bot\n\n"
            "Query crypto prices with these commands:\n\n"
            "• /p <symbol> — Query token price\n"
            "• /price <symbol> — Query token price\n"
            "• $<symbol> — Quick query (e.g. $BTC)\n\n"
            "Examples: /p btc, /price eth, $sol\n\n"
            "Click the 🌐 button below any message to switch language."
        ),
        "zh": (
            "📖 BitBaby 报价机器人\n\n"
            "使用以下指令查询代币价格：\n\n"
            "• /p <代币> — 查询代币价格\n"
            "• /price <代币> — 查询代币价格\n"
            "• $<代币> — 快捷查询（如 $BTC）\n\n"
            "示例：/p btc、/price eth、$sol\n\n"
            "点击消息下方的 🌐 按钮切换语言。"
        ),
    },
    "welcome": {
        "en": (
            "👋 Welcome to BitBaby Price Bot!\n\n"
            "I can help you check real-time crypto prices.\n"
            "Use /help to see all commands.\n\n"
            "Try: /p btc or $eth"
        ),
        "zh": (
            "👋 欢迎使用 BitBaby 报价机器人！\n\n"
            "我可以帮你查询实时加密货币价格。\n"
            "使用 /help 查看所有指令。\n\n"
            "试试：/p btc 或 $eth"
        ),
    },
    "lang_switched": {"en": "✅ Language switched to English", "zh": "✅ 语言已切换为中文"},
    "error": {"en": "⚠️ Failed to fetch price data. Please try again later.", "zh": "⚠️ 获取价格数据失败，请稍后重试。"},
}

# Simple in-memory lang store (Vercel functions are stateless,
# so we use callback_data to carry state instead)
_chat_lang: dict[int, str] = {}


def t(key: str, lang: str = "en", **kwargs) -> str:
    entry = TEXTS.get(key, {})
    text = entry.get(lang, entry.get("en", f"[missing: {key}]"))
    if kwargs:
        text = text.format(**kwargs)
    return text


# ─── Formatters ───────────────────────────────────────────────────

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


# ─── CoinGecko ────────────────────────────────────────────────────

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


# ─── Telegram API Helpers ─────────────────────────────────────────

def build_trade_url(symbol: str) -> str:
    if TRADE_URL_MODE == "pair":
        return f"{TRADE_URL}/trade/{symbol.upper()}_USDT"
    return TRADE_URL


def price_keyboard(symbol: str, lang: str) -> list:
    """InlineKeyboardMarkup as dict for Telegram API."""
    trade_url = build_trade_url(symbol)
    target_lang = "zh" if lang == "en" else "en"
    return {
        "inline_keyboard": [
            [{"text": t("btn_trade", lang), "url": trade_url}],
            [{"text": t("btn_lang_switch", lang), "callback_data": f"lang:{target_lang}:{symbol}"}],
        ]
    }


def simple_keyboard(lang: str, msg_type: str = "help") -> dict:
    target_lang = "zh" if lang == "en" else "en"
    return {
        "inline_keyboard": [
            [{"text": t("btn_lang_switch", lang), "callback_data": f"slang:{target_lang}:{msg_type}"}],
        ]
    }


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


# ─── Bot Logic ────────────────────────────────────────────────────

async def handle_message(msg: dict):
    """Process an incoming message."""
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()
    lang = _chat_lang.get(chat_id, DEFAULT_LANG)

    # /start
    if text.startswith("/start"):
        await tg_send(chat_id, t("welcome", lang), simple_keyboard(lang, "welcome"))
        return

    # /help
    if text.startswith("/help"):
        await tg_send(chat_id, t("help", lang), simple_keyboard(lang, "help"))
        return

    # /lang en | /lang zh
    if text.startswith("/lang"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].lower() in ("en", "zh"):
            new_lang = parts[1].lower()
            _chat_lang[chat_id] = new_lang
            await tg_send(chat_id, t("lang_switched", new_lang), simple_keyboard(new_lang, "help"))
        else:
            await tg_send(chat_id, "Usage: /lang en | /lang zh")
        return

    # /p <symbol> or /price <symbol>
    if text.startswith("/p ") or text.startswith("/price "):
        parts = text.split()
        if len(parts) >= 2:
            symbol = parts[1].upper()
            await query_and_reply(chat_id, symbol, lang)
        else:
            await tg_send(chat_id, t("help", lang), simple_keyboard(lang, "help"))
        return

    # /p@botname <symbol> (群组中带 bot 用户名的指令)
    if text.startswith("/p@") or text.startswith("/price@"):
        parts = text.split()
        if len(parts) >= 2:
            symbol = parts[1].upper()
            await query_and_reply(chat_id, symbol, lang)
        return

    # $BTC style
    matches = re.findall(r"\$([A-Za-z0-9]{1,10})", text)
    if matches:
        symbol = matches[0].upper()
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
            _chat_lang[chat_id] = new_lang

            price_data = await fetch_price(symbol)
            if price_data:
                text = build_price_msg(price_data, new_lang)
                kb = price_keyboard(symbol, new_lang)
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
            _chat_lang[chat_id] = new_lang

            if msg_type == "welcome":
                text = t("welcome", new_lang)
            else:
                text = t("help", new_lang)
            await tg_edit(chat_id, message_id, text, simple_keyboard(new_lang, msg_type))


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
    kb = price_keyboard(symbol, lang)
    await tg_send(chat_id, text, kb)


# ─── Vercel Handler ──────────────────────────────────────────────

import asyncio


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

        # Route to appropriate handler
        if "message" in update:
            asyncio.run(handle_message(update["message"]))
        elif "callback_query" in update:
            asyncio.run(handle_callback_query(update["callback_query"]))

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "BitBaby Price Bot is running"}')
