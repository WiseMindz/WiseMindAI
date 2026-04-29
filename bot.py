import asyncio
import logging
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
from config import (
    TELEGRAM_BOT_TOKEN,
    CLAUDE_API_KEY,
    CLAUDE_MODEL_FAST,
    CLAUDE_MODEL_SMART,
)
from database import (
    init_db,
    get_last_trade,
    save_message,
    get_recent_messages,
    cleanup_old_messages,
)
from system_prompt import SYSTEM_PROMPT

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

claude = Anthropic(api_key=CLAUDE_API_KEY)


# ==================== SMART ROUTING ====================
SMART_KEYWORDS = [
    "strategi", "setup", "trade", "trades", "entry", "entries", "exit",
    "killzone", "killzon", "sweep", "displacement", "manipulation",
    "fvg", "ob", "order block", "liquidity", "asia", "london", "ny",
    "t1", "t2", "amd", "session",
    "analysera", "analys", "förklara", "djupgående", "detaljerat",
    "skillnad", "varför", "hur kommer det sig",
    "psykologi", "disciplin", "känslor", "frustrerad", "revenge",
    "förlust", "förlorade", "drawdown", "tilt", "stressad",
    "risk", "riskhantering", "lot size", "lotsize", "position size",
    "strategy", "explain", "analyze", "analysis", "psychology",
    "feedback", "review", "discipline", "lost", "losing",
]

FORCE_FAST_PREFIX = "[snabb]"
FORCE_SMART_PREFIX = "[smart]"


def pick_model(user_text: str) -> tuple[str, str]:
    text_lower = user_text.lower().strip()
    if text_lower.startswith(FORCE_FAST_PREFIX):
        return CLAUDE_MODEL_FAST, "user-forced fast"
    if text_lower.startswith(FORCE_SMART_PREFIX):
        return CLAUDE_MODEL_SMART, "user-forced smart"
    if len(user_text) > 200:
        return CLAUDE_MODEL_SMART, f"long ({len(user_text)} chars)"
    for keyword in SMART_KEYWORDS:
        if keyword in text_lower:
            return CLAUDE_MODEL_SMART, f"keyword '{keyword}'"
    return CLAUDE_MODEL_FAST, "short/casual"


def strip_force_prefix(user_text: str) -> str:
    text_lower = user_text.lower().strip()
    if text_lower.startswith(FORCE_FAST_PREFIX):
        return user_text.strip()[len(FORCE_FAST_PREFIX):].strip()
    if text_lower.startswith(FORCE_SMART_PREFIX):
        return user_text.strip()[len(FORCE_SMART_PREFIX):].strip()
    return user_text


# ==================== KONVERSATIONSMINNE → CLAUDE FORMAT ====================

def build_messages_for_claude(history: list, current_user_text: str, current_username: str) -> list:
    """
    Bygger Claude API messages-array från databas-historik + nuvarande fråga.

    Claude API kräver alternerande user/assistant roles. Vi lägger till
    avsändarens namn i text-prefix så Claude förstår vem som säger vad i gruppen.
    """
    messages = []
    last_role = None

    for msg in history:
        role = msg["role"]
        username = msg["username"] or "okänd"
        text = msg["text"]

        # Prefixera namn för user-meddelanden (assistent har inget namn-prefix)
        if role == "user":
            content = f"[{username}]: {text}"
        else:
            content = text

        # Slå ihop konsekutiva meddelanden från samma roll (Claude API kräver alternering)
        if role == last_role and messages:
            messages[-1]["content"] += f"\n{content}"
        else:
            messages.append({"role": role, "content": content})
            last_role = role

    # Lägg till nuvarande meddelande
    current_content = f"[{current_username}]: {current_user_text}"
    if last_role == "user" and messages:
        messages[-1]["content"] += f"\n{current_content}"
    else:
        messages.append({"role": "user", "content": current_content})

    return messages


# ==================== CLAUDE RESPONSE ====================
async def claude_response(user_text: str, chat_id: int, username: str):
    """Call Claude API with conversation memory + smart routing."""
    try:
        model, reason = pick_model(user_text)
        clean_text = strip_force_prefix(user_text)
        max_tokens = 800 if model == CLAUDE_MODEL_FAST else 1500

        # Hämta senaste 20 meddelanden för kontext
        history = await get_recent_messages(chat_id, limit=20)

        # Hämta senaste trade som extra kontext
        last_trade = await get_last_trade()
        trade_context = f"\n\nSenaste trade i systemet: {last_trade}" if last_trade else ""

        # Bygg system prompt med trade-kontext
        full_system = SYSTEM_PROMPT + trade_context

        # Bygg messages-array med konversationshistorik
        messages = build_messages_for_claude(history, clean_text, username)

        logger.info(f"Routing → {model.split('-')[1].upper()} ({reason}) | history={len(history)} msgs | input_len={len(clean_text)}")

        start = time.time()
        response = claude.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=full_system,
            messages=messages,
        )
        elapsed = time.time() - start

        response_text = response.content[0].text
        logger.info(f"Claude response — {model.split('-')[1].upper()} | {elapsed:.1f}s | response_len={len(response_text)}")
        return response_text

    except Exception as e:
        logger.error(f"Claude API call failed: {type(e).__name__}: {e}")
        return "⚠️ Jag kunde inte hämta svar från Claude just nu. Försök igen om en stund."


# ==================== KOMMANDON ====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start from user {update.effective_user.id}")
    await update.message.reply_text("✅ WiseMind AI är online och redo!")


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/last from user {update.effective_user.id}")
    try:
        trade = await get_last_trade()
        if trade:
            text = f"📊 *Senaste trade*\n{trade.get('symbol')} {trade.get('direction', '').upper()} @ {trade.get('entry')}"
        else:
            text = "📭 Inga trades än."
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/last command failed: {e}")
        await update.message.reply_text("⚠️ Kunde inte hämta senaste trade.")


async def cmd_clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rensa konversationsminne för denna chat (bara senaste 100 sparas ändå)"""
    logger.info(f"/clearmemory from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        await cleanup_old_messages(update.effective_chat.id, keep_last=0)
        await update.message.reply_text("🧹 Konversationsminne rensat för denna chat.")
    except Exception as e:
        logger.error(f"/clearmemory failed: {e}")
        await update.message.reply_text("⚠️ Kunde inte rensa minnet.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spara ALLA meddelanden, svara endast när taggad."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username or "okänd"
    text = update.message.text
    text_lower = text.lower()

    # SPARA ALLTID — boten ska se hela konversationen
    try:
        await save_message(chat_id, user_id, username, "user", text)
    except Exception as e:
        logger.error(f"Failed to save message: {e}")

    # Svara bara om taggad
    if "@wisefx_bot" in text_lower or "wisemind" in text_lower:
        logger.info(f"Bot tagged by {username} ({user_id}) in chat {chat_id}: {text[:80]}")
        try:
            response = await claude_response(text, chat_id, username)
            await update.message.reply_text(response)

            # Spara bot-svaret som en del av minnet
            try:
                await save_message(chat_id, None, "WiseMind AI", "assistant", response)
            except Exception as e:
                logger.error(f"Failed to save bot reply: {e}")

            # Periodisk cleanup — behåll bara senaste 100 per chat
            try:
                await cleanup_old_messages(chat_id, keep_last=100)
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

            logger.info("Reply sent successfully")
        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            try:
                await update.message.reply_text("⚠️ Något gick fel när jag försökte svara.")
            except Exception:
                pass


# ==================== ERROR HANDLER ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)


# ==================== START ====================
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(init_db())
        logger.info("Database initialized (with conversation memory)")

        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("last", cmd_last))
        app.add_handler(CommandHandler("clearmemory", cmd_clear_memory))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)

        logger.info("WiseMind AI starting... (smart routing + conversation memory)")
        logger.info("Bot is running and listening")
        logger.info("Try: @Wisefx_bot hej")

        app.run_polling(drop_pending_updates=True)

    finally:
        loop.close()


if __name__ == "__main__":
    main()
