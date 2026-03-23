"""
Vercel Serverless Function — Telegram Bot Webhook Handler.

Uses only Python stdlib (urllib) — no third-party dependencies needed.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error
from http.server import BaseHTTPRequestHandler

# ─── Config ───────────────────────────────────────────────────────

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
COINGECKO_API = "https://api.coingecko.com/api/v3"

REDIS_BUTTONS_KEY = "bitbaby:buttons"
REDIS_LANG_PREFIX = "bitbaby:lang:"

# ─── HTTP Helper ──────────────────────────────────────────────────

def http_get(url, headers=None):
    """Simple HTTP GET returning parsed JSON or None."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def http_post_json(url, data, headers=None):
    """HTTP POST with JSON body."""
    try:
        body = json.dumps(data).encode()
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"_error": str(e)}


def http_post_form(url, data):
    """HTTP POST with form data."""
    try:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


# ─── CoinGecko Symbol Mapping ────────────────────────────────────

SYMBOL_TO_ID = {
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
        "en": '❌ Token "{symbol}" not found.',
        "zh": '❌ 未找到代币 "{symbol}"。',
    },
    "help": {
        "en": (
            "📖 BitBaby Price Bot\n\n"
            "• /p <symbol> — Query price\n"
            "• /p btc eth sol — Multi query\n"
            "• $BTC — Quick query\n"
            "• /trending — Trending coins\n"
            "• /lang en|zh — Switch language\n\n"
            "Click 🌐 to switch language."
        ),
        "zh": (
            "📖 BitBaby 报价机器人\n\n"
            "• /p <代币> — 查询价格\n"
            "• /p btc eth sol — 多币种查询\n"
            "• $BTC — 快捷查询\n"
            "• /trending — 热门代币\n"
            "• /lang en|zh — 切换语言\n\n"
            "点击 🌐 切换语言。"
        ),
    },
    "admin_help": {
        "en": (
            "🔧 Admin Commands:\n\n"
            "• /addbutton EN text | 中文 | URL\n"
            "• /editbutton <num> EN | 中文 | URL\n"
            "• /removebutton <num>\n"
            "• /listbuttons\n"
            "• /clearbuttons\n\n"
            "Example:\n"
            "/addbutton 🚀 Trade on BitBaby | 🚀 去 BitBaby 交易 | https://www.bitbaby.com/en-us"
        ),
        "zh": (
            "🔧 管理员指令：\n\n"
            "• /addbutton 英文文字 | 中文文字 | 链接\n"
            "• /editbutton <编号> 英文 | 中文 | 链接\n"
            "• /removebutton <编号>\n"
            "• /listbuttons\n"
            "• /clearbuttons\n\n"
            "示例：\n"
            "/addbutton 🚀 Trade on BitBaby | 🚀 去 BitBaby 交易 | https://www.bitbaby.com/en-us"
        ),
    },
    "welcome": {
        "en": "👋 Welcome to BitBaby Price Bot!\n\nUse /help to see commands.\nTry: /p btc or $eth",
        "zh": "👋 欢迎使用 BitBaby 报价机器人！\n\n使用 /help 查看指令。\n试试：/p btc 或 $eth",
    },
    "lang_switched":   {"en": "✅ Language switched to English", "zh": "✅ 语言已切换为中文"},
    "error":           {"en": "⚠️ Error. Try again later.", "zh": "⚠️ 出错了，请稍后重试。"},
    "no_permission":   {"en": "🚫 Admin only.", "zh": "🚫 仅管理员可用。"},
    "btn_added":       {"en": "✅ Button added: {text}", "zh": "✅ 按钮已添加：{text}"},
    "btn_edited":      {"en": "✅ Button #{num} updated: {text}", "zh": "✅ 按钮 #{num} 已更新：{text}"},
    "btn_removed":     {"en": "✅ Button #{num} removed.", "zh": "✅ 按钮 #{num} 已删除。"},
    "btn_cleared":     {"en": "✅ All buttons cleared.", "zh": "✅ 所有按钮已清空。"},
    "btn_list_empty":  {"en": "📋 No buttons yet. Use /addbutton", "zh": "📋 还没有按钮。使用 /addbutton 添加"},
    "btn_invalid_fmt": {
        "en": "❌ Format: /addbutton EN text | 中文文字 | URL",
        "zh": "❌ 格式：/addbutton 英文文字 | 中文文字 | 链接",
    },
    "btn_invalid_num": {"en": "❌ Invalid number.", "zh": "❌ 无效编号。"},
    "trending_title":  {"en": "🔥 Trending Coins", "zh": "🔥 热门代币"},
    "trending_empty":  {"en": "No trending data.", "zh": "暂无热门数据。"},
    "multi_query_max": {"en": "⚠️ Max 5 tokens.", "zh": "⚠️ 最多查 5 个。"},
}


def t(key, lang="en", **kw):
    entry = TEXTS.get(key, {})
    text = entry.get(lang, entry.get("en", f"[{key}]"))
    if kw:
        text = text.format(**kw)
    return text


# ─── Redis ───────────────────────────────────────────────────────

def redis_get(key):
    if not UPSTASH_URL:
        return None
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    data = http_get(f"{UPSTASH_URL}/get/{key}", headers)
    return data.get("result") if data else None


def redis_set(key, value):
    if not UPSTASH_URL:
        return None
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    result = http_post_json(f"{UPSTASH_URL}", ["SET", key, value], headers)
    return result


def redis_del(key):
    if not UPSTASH_URL:
        return False
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    return http_post_json(f"{UPSTASH_URL}", ["DEL", key], headers) is not None


def get_buttons():
    raw = redis_get(REDIS_BUTTONS_KEY)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def save_buttons(buttons):
    return redis_set(REDIS_BUTTONS_KEY, json.dumps(buttons))


def get_lang(chat_id):
    result = redis_get(f"{REDIS_LANG_PREFIX}{chat_id}")
    return result if result in ("en", "zh") else DEFAULT_LANG


def set_lang(chat_id, lang):
    redis_set(f"{REDIS_LANG_PREFIX}{chat_id}", lang)


# ─── Formatters ──────────────────────────────────────────────────

def fmt_num(v):
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


def fmt_change(v):
    if v is None:
        return "N/A"
    arrow = "📈" if v >= 0 else "📉"
    return f"{arrow} {v:+.2f}"


# ─── CoinGecko ───────────────────────────────────────────────────

def search_coin_id(symbol):
    sym = symbol.lower().strip()
    if sym in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[sym]
    q = urllib.parse.urlencode({"query": sym})
    data = http_get(f"{COINGECKO_API}/search?{q}")
    if not data:
        return None
    for c in data.get("coins", []):
        if c.get("symbol", "").lower() == sym:
            return c["id"]
    coins = data.get("coins", [])
    return coins[0]["id"] if coins else None


def fetch_price(symbol):
    coin_id = search_coin_id(symbol)
    if not coin_id:
        return None
    q = urllib.parse.urlencode({
        "localization": "false", "tickers": "false",
        "community_data": "false", "developer_data": "false", "sparkline": "false",
    })
    data = http_get(f"{COINGECKO_API}/coins/{coin_id}?{q}")
    if not data:
        return None
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


def fetch_trending():
    data = http_get(f"{COINGECKO_API}/search/trending")
    if not data:
        return []
    results = []
    for item in data.get("coins", [])[:10]:
        coin = item.get("item", {})
        results.append({
            "name": coin.get("name", ""),
            "symbol": coin.get("symbol", "").upper(),
            "rank": coin.get("market_cap_rank"),
        })
    return results


# ─── Message Builder ─────────────────────────────────────────────

def build_price_msg(data, lang):
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


# ─── Keyboards ───────────────────────────────────────────────────

def price_keyboard(symbol, lang):
    buttons = get_buttons()
    keyboard = []
    for btn in buttons:
        # Support bilingual: {"text_en": "...", "text_zh": "...", "url": "..."}
        # Also backward compatible with old format: {"text": "...", "url": "..."}
        if "text_en" in btn:
            btn_text = btn["text_zh"] if lang == "zh" else btn["text_en"]
        else:
            btn_text = btn.get("text", "")
        keyboard.append([{"text": btn_text, "url": btn["url"]}])
    target_lang = "zh" if lang == "en" else "en"
    keyboard.append([{
        "text": t("btn_lang_switch", lang),
        "callback_data": f"lang:{target_lang}:{symbol}",
    }])
    return {"inline_keyboard": keyboard}


def simple_keyboard(lang, msg_type="help"):
    target_lang = "zh" if lang == "en" else "en"
    return {"inline_keyboard": [[{
        "text": t("btn_lang_switch", lang),
        "callback_data": f"slang:{target_lang}:{msg_type}",
    }]]}


# ─── Telegram API ────────────────────────────────────────────────

def tg_send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    http_post_json(f"{TELEGRAM_API}/sendMessage", payload)


def tg_edit(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    http_post_json(f"{TELEGRAM_API}/editMessageText", payload)


def tg_answer_callback(callback_query_id):
    http_post_json(f"{TELEGRAM_API}/answerCallbackQuery",
                   {"callback_query_id": callback_query_id})


def tg_answer_inline(inline_query_id, results):
    http_post_json(f"{TELEGRAM_API}/answerInlineQuery", {
        "inline_query_id": inline_query_id,
        "results": results,
        "cache_time": 30,
    })


# ─── Admin Helpers ───────────────────────────────────────────────

def is_admin(user_id):
    return user_id in ADMIN_IDS


def parse_button_input(text):
    """Parse 'EN text | 中文文字 | URL' or 'text | URL' format.
    Returns (text_en, text_zh, url) or None.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) == 3:
        # EN text | ZH text | URL
        if parts[0] and parts[1] and parts[2]:
            return (parts[0], parts[1], parts[2])
    elif len(parts) == 2:
        # Same text for both | URL
        if parts[0] and parts[1]:
            return (parts[0], parts[0], parts[1])
    return None


# ─── Bot Logic ───────────────────────────────────────────────────

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id", 0)
    text = msg.get("text", "").strip()
    if not text:
        return
    lang = get_lang(chat_id)

    # /start
    if text.startswith("/start"):
        tg_send(chat_id, t("welcome", lang), simple_keyboard(lang, "welcome"))
        return

    # /help
    if text.startswith("/help"):
        help_text = t("help", lang)
        if is_admin(user_id):
            help_text += "\n\n" + t("admin_help", lang)
        tg_send(chat_id, help_text, simple_keyboard(lang, "help"))
        return

    # /lang
    if text.startswith("/lang"):
        parts = text.split()
        if len(parts) >= 2 and parts[1].lower() in ("en", "zh"):
            new_lang = parts[1].lower()
            set_lang(chat_id, new_lang)
            tg_send(chat_id, t("lang_switched", new_lang), simple_keyboard(new_lang, "help"))
        else:
            tg_send(chat_id, "Usage: /lang en | /lang zh")
        return

    # ── Admin Commands ──

    if text.startswith("/addbutton"):
        if not is_admin(user_id):
            tg_send(chat_id, t("no_permission", lang))
            return
        content = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
        parsed = parse_button_input(content)
        if not parsed:
            tg_send(chat_id, t("btn_invalid_fmt", lang))
            return
        text_en, text_zh, btn_url = parsed
        buttons = get_buttons()
        buttons.append({"text_en": text_en, "text_zh": text_zh, "url": btn_url})
        result = save_buttons(buttons)
        debug = f"\n\n[DEBUG] Redis response: {result}\n[DEBUG] UPSTASH_URL set: {bool(UPSTASH_URL)}"
        tg_send(chat_id, t("btn_added", lang, text=f"{text_en} / {text_zh}") + debug)
        return

    if text.startswith("/editbutton"):
        if not is_admin(user_id):
            tg_send(chat_id, t("no_permission", lang))
            return
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            tg_send(chat_id, "Usage: /editbutton <num> <text> | <url>")
            return
        try:
            idx = int(parts[1]) - 1
        except ValueError:
            tg_send(chat_id, t("btn_invalid_num", lang))
            return
        parsed = parse_button_input(parts[2])
        if not parsed:
            tg_send(chat_id, t("btn_invalid_fmt", lang))
            return
        buttons = get_buttons()
        if idx < 0 or idx >= len(buttons):
            tg_send(chat_id, t("btn_invalid_num", lang))
            return
        text_en, text_zh, btn_url = parsed
        buttons[idx] = {"text_en": text_en, "text_zh": text_zh, "url": btn_url}
        save_buttons(buttons)
        tg_send(chat_id, t("btn_edited", lang, num=idx + 1, text=f"{text_en} / {text_zh}"))
        return

    if text.startswith("/removebutton"):
        if not is_admin(user_id):
            tg_send(chat_id, t("no_permission", lang))
            return
        parts = text.split()
        if len(parts) < 2:
            tg_send(chat_id, "Usage: /removebutton <num>")
            return
        try:
            idx = int(parts[1]) - 1
        except ValueError:
            tg_send(chat_id, t("btn_invalid_num", lang))
            return
        buttons = get_buttons()
        if idx < 0 or idx >= len(buttons):
            tg_send(chat_id, t("btn_invalid_num", lang))
            return
        buttons.pop(idx)
        save_buttons(buttons)
        tg_send(chat_id, t("btn_removed", lang, num=idx + 1))
        return

    if text.startswith("/listbuttons"):
        if not is_admin(user_id):
            tg_send(chat_id, t("no_permission", lang))
            return
        buttons = get_buttons()
        if not buttons:
            tg_send(chat_id, t("btn_list_empty", lang))
            return
        lines = ["📋 Current Buttons:" if lang == "en" else "📋 当前按钮：", ""]
        for i, btn in enumerate(buttons, 1):
            if "text_en" in btn:
                lines.append(f"{i}. EN: {btn['text_en']}\n   ZH: {btn['text_zh']}\n   → {btn['url']}")
            else:
                lines.append(f"{i}. {btn.get('text', '?')}\n   → {btn['url']}")
        tg_send(chat_id, "\n".join(lines))
        return

    if text.startswith("/clearbuttons"):
        if not is_admin(user_id):
            tg_send(chat_id, t("no_permission", lang))
            return
        redis_del(REDIS_BUTTONS_KEY)
        tg_send(chat_id, t("btn_cleared", lang))
        return

    # /trending
    if text.startswith("/trending"):
        handle_trending(chat_id, lang)
        return

    # /p or /price (multi-token)
    if text.startswith("/p ") or text.startswith("/price "):
        parts = text.split()
        symbols = [s.upper() for s in parts[1:] if s and not s.startswith("/")]
        if not symbols:
            tg_send(chat_id, t("help", lang), simple_keyboard(lang, "help"))
            return
        if len(symbols) > 5:
            tg_send(chat_id, t("multi_query_max", lang))
            symbols = symbols[:5]
        for sym in symbols:
            query_and_reply(chat_id, sym, lang)
        return

    # /p@botname
    if text.startswith("/p@") or text.startswith("/price@"):
        parts = text.split()
        for sym in [s.upper() for s in parts[1:]][:5]:
            query_and_reply(chat_id, sym, lang)
        return

    # $BTC style
    matches = re.findall(r"\$([A-Za-z0-9]{1,10})", text)
    if matches:
        for sym in [m.upper() for m in matches[:5]]:
            query_and_reply(chat_id, sym, lang)


def handle_callback_query(cbq):
    callback_id = cbq["id"]
    data = cbq.get("data", "")
    chat_id = cbq["message"]["chat"]["id"]
    message_id = cbq["message"]["message_id"]

    tg_answer_callback(callback_id)

    if data.startswith("lang:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            new_lang, symbol = parts[1], parts[2]
            set_lang(chat_id, new_lang)
            price_data = fetch_price(symbol)
            if price_data:
                text = build_price_msg(price_data, new_lang)
                kb = price_keyboard(symbol, new_lang)
                tg_edit(chat_id, message_id, text, kb)
            else:
                tg_edit(chat_id, message_id,
                        t("not_found", new_lang, symbol=symbol),
                        simple_keyboard(new_lang))

    elif data.startswith("slang:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            new_lang, msg_type = parts[1], parts[2]
            set_lang(chat_id, new_lang)
            if msg_type == "welcome":
                text = t("welcome", new_lang)
            else:
                text = t("help", new_lang)
            tg_edit(chat_id, message_id, text, simple_keyboard(new_lang, msg_type))


def handle_trending(chat_id, lang):
    coins = fetch_trending()
    if not coins:
        tg_send(chat_id, t("trending_empty", lang))
        return
    lines = [t("trending_title", lang), "━" * 24]
    for i, coin in enumerate(coins, 1):
        rank_str = f"#{coin['rank']}" if coin.get("rank") else "—"
        lines.append(f"{i}. {coin['name']} ({coin['symbol']})  [{rank_str}]")
    tip = "\n💡 输入 /p <代币> 查看详情" if lang == "zh" else "\n💡 Use /p <symbol> for details"
    lines.append(tip)
    tg_send(chat_id, "\n".join(lines), simple_keyboard(lang, "help"))


def query_and_reply(chat_id, symbol, lang):
    try:
        price_data = fetch_price(symbol)
    except Exception:
        tg_send(chat_id, t("error", lang))
        return
    if not price_data:
        tg_send(chat_id, t("not_found", lang, symbol=symbol), simple_keyboard(lang))
        return
    text = build_price_msg(price_data, lang)
    kb = price_keyboard(symbol, lang)
    tg_send(chat_id, text, kb)


def handle_inline_query(iq):
    query_id = iq["id"]
    query_text = iq.get("query", "").strip()
    if not query_text:
        tg_answer_inline(query_id, [])
        return
    price_data = fetch_price(query_text)
    if not price_data:
        tg_answer_inline(query_id, [])
        return
    msg_text = build_price_msg(price_data, DEFAULT_LANG)
    buttons = get_buttons()
    keyboard = []
    for b in buttons:
        bt = b.get("text_en", b.get("text", ""))
        keyboard.append([{"text": bt, "url": b["url"]}])
    result = {
        "type": "article",
        "id": f"price_{price_data['symbol']}",
        "title": f"{price_data['name']} ({price_data['symbol']})",
        "description": f"${fmt_num(price_data['price_usd'])}",
        "input_message_content": {"message_text": msg_text},
    }
    if keyboard:
        result["reply_markup"] = {"inline_keyboard": keyboard}
    tg_answer_inline(query_id, [result])


# ─── Vercel Handler ──────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

        try:
            update = json.loads(body)
        except Exception:
            return

        try:
            if "message" in update:
                handle_message(update["message"])
            elif "callback_query" in update:
                handle_callback_query(update["callback_query"])
            elif "inline_query" in update:
                handle_inline_query(update["inline_query"])
        except Exception:
            pass  # Silently handle errors to avoid 500

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"BitBaby Price Bot is running"}')

    def log_message(self, format, *args):
        pass  # Suppress default logging
