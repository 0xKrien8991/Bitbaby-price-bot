"""BitBaby Telegram Price Bot - Main bot logic."""

import logging
import os
import re

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from coingecko import fetch_price
from i18n import build_price_message, t

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TRADE_URL = os.getenv("TRADE_URL", "https://www.bitbaby.com/en-us")
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "en")

# Per-chat language preference stored in memory (resets on restart)
# For production, consider using a database
chat_lang: dict[int, str] = {}


def get_lang(chat_id: int) -> str:
    """Get the language preference for a chat."""
    return chat_lang.get(chat_id, DEFAULT_LANG)


def build_trade_url(symbol: str) -> str:
    """Build the trade URL for a given symbol.

    Supports two modes via TRADE_URL_MODE env var:
    - "direct": just use TRADE_URL as-is (default)
    - "pair":   append /trade/SYMBOL_USDT to TRADE_URL
    """
    mode = os.getenv("TRADE_URL_MODE", "direct")
    if mode == "pair":
        return f"{TRADE_URL}/trade/{symbol.upper()}_USDT"
    return TRADE_URL


def make_price_keyboard(symbol: str, lang: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with trade button and language switch."""
    trade_url = build_trade_url(symbol)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=t("btn_trade", lang),
                    url=trade_url,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_lang_switch", lang),
                    callback_data=f"lang_switch:{symbol}",
                ),
            ],
        ]
    )


def make_simple_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with only language switch (for help/welcome)."""
    target_lang = "zh" if lang == "en" else "en"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=t("btn_lang_switch", lang),
                    callback_data=f"lang_simple:{target_lang}",
                ),
            ],
        ]
    )


# ── Command Handlers ──────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    await update.message.reply_text(
        t("welcome", lang),
        parse_mode="Markdown",
        reply_markup=make_simple_keyboard(lang),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)
    await update.message.reply_text(
        t("help", lang),
        parse_mode="Markdown",
        reply_markup=make_simple_keyboard(lang),
    )


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /p and /price commands."""
    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)

    if not context.args:
        await update.message.reply_text(t("help", lang), parse_mode="Markdown")
        return

    symbol = context.args[0].strip().upper()
    await _query_and_reply(update, symbol, lang)


async def cmd_set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lang command to set language. Usage: /lang en or /lang zh"""
    chat_id = update.effective_chat.id
    if context.args and context.args[0].lower() in ("en", "zh"):
        new_lang = context.args[0].lower()
        chat_lang[chat_id] = new_lang
        await update.message.reply_text(
            t("lang_switched", new_lang),
            reply_markup=make_simple_keyboard(new_lang),
        )
    else:
        lang = get_lang(chat_id)
        await update.message.reply_text(
            "Usage: /lang en | /lang zh",
            reply_markup=make_simple_keyboard(lang),
        )


# ── Message Handler (for $SYMBOL pattern) ────────────────────────


async def handle_dollar_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle $SYMBOL style queries in chat messages."""
    if not update.message or not update.message.text:
        return

    # Match $BTC, $eth, etc.
    matches = re.findall(r"\$([A-Za-z0-9]{1,10})", update.message.text)
    if not matches:
        return

    chat_id = update.effective_chat.id
    lang = get_lang(chat_id)

    # Only process the first match to avoid spam
    symbol = matches[0].upper()
    await _query_and_reply(update, symbol, lang)


# ── Callback Query Handler (inline button clicks) ────────────────


async def handle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle inline keyboard button callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_chat.id

    if data.startswith("lang_switch:"):
        # Toggle language and re-fetch price
        symbol = data.split(":", 1)[1]
        current_lang = get_lang(chat_id)
        new_lang = "zh" if current_lang == "en" else "en"
        chat_lang[chat_id] = new_lang

        # Re-fetch and update the message
        price_data = await fetch_price(symbol)
        if price_data:
            text = build_price_message(price_data, new_lang)
            keyboard = make_price_keyboard(symbol, new_lang)
            await query.edit_message_text(text=text, reply_markup=keyboard)
        else:
            await query.edit_message_text(
                text=t("not_found", new_lang, symbol=symbol),
                reply_markup=make_simple_keyboard(new_lang),
            )

    elif data.startswith("lang_simple:"):
        # Toggle language for help/welcome messages
        new_lang = data.split(":", 1)[1]
        chat_lang[chat_id] = new_lang

        # Determine if this was a help or welcome message and update
        old_text = query.message.text or ""
        if "Price Bot" in old_text or "报价机器人" in old_text:
            if "Welcome" in old_text or "欢迎" in old_text:
                new_text = t("welcome", new_lang)
            else:
                new_text = t("help", new_lang)
        else:
            new_text = t("lang_switched", new_lang)

        await query.edit_message_text(
            text=new_text,
            parse_mode="Markdown",
            reply_markup=make_simple_keyboard(new_lang),
        )


# ── Shared Helper ─────────────────────────────────────────────────


async def _query_and_reply(update: Update, symbol: str, lang: str) -> None:
    """Fetch price and send response with inline keyboard."""
    try:
        price_data = await fetch_price(symbol)
    except Exception:
        logger.exception("Failed to fetch price for %s", symbol)
        await update.message.reply_text(t("error", lang))
        return

    if not price_data:
        await update.message.reply_text(
            t("not_found", lang, symbol=symbol),
            reply_markup=make_simple_keyboard(lang),
        )
        return

    text = build_price_message(price_data, lang)
    keyboard = make_price_keyboard(symbol, lang)
    await update.message.reply_text(text=text, reply_markup=keyboard)


# ── Main ──────────────────────────────────────────────────────────


def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set! Check your .env file.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler(["p", "price"], cmd_price))
    app.add_handler(CommandHandler("lang", cmd_set_lang))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    # $SYMBOL pattern in messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dollar_query))

    logger.info("BitBaby Price Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
