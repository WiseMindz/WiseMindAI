"""
WiseMind AI — Telegram bot + FastAPI webhook (unified async architecture)

v9.21+ improvements:
- Webhook + bot run on SAME asyncio event loop (no threading race conditions)
- Proper graceful shutdown
- Logs everything clearly so Railway deploy logs show all startup steps
"""

import asyncio
import logging
import os
import time
from datetime import datetime

import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import AsyncAnthropic

from config import (
    TELEGRAM_BOT_TOKEN,
    CLAUDE_API_KEY,
    CLAUDE_MODEL_FAST,
    CLAUDE_MODEL_SMART,
    WEBHOOK_PORT,
)
from database import (
    init_db,
    get_last_trade,
    get_recent_trades,
    save_message,
    get_recent_messages,
    cleanup_old_messages,
)
from media_utils import (
    download_telegram_file,
    extract_text_from_image,
    extract_text_from_document,
    is_image_file,
    is_text_file,
    sanitize_filename,
)
from system_prompt import SYSTEM_PROMPT
from signal_utils import evaluate_signal, extract_signal_data_from_text
from webhook_handler import app as webhook_app

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

claude = AsyncAnthropic(api_key=CLAUDE_API_KEY)


# ==================== SMART ROUTING ====================
SMART_KEYWORDS = [
    # Setup & structure
    "strategi", "setup", "trade", "trades", "entry", "entries", "exit",
    "killzone", "killzon", "sweep", "displacement", "manipulation",
    "fvg", "ob", "order block", "orderblock", "liquidity", "asia", "london", "ny",
    "t1", "t2", "amd", "session", "breaker", "mitigation", "imbalance",
    "bpr", "ifvg", "choch", "mss", "bos", "cisd", "inducement",
    "premium", "discount", "pd array", "dealing range", "equilibrium",
    "smart money", "icт", "ict", "internal", "external", "swing",
    "htf", "ltf", "higher time", "lower time", "confluence",
    # Analysis requests
    "analysera", "analys", "förklara", "djupgående", "detaljerat",
    "skillnad", "varför", "hur kommer det sig", "vad betyder",
    "explain", "analyze", "analysis", "what is", "how does", "why did",
    "review", "feedback", "evaluate", "rate my",
    # Psychology & discipline
    "psykologi", "disciplin", "känslor", "frustrerad", "revenge",
    "förlust", "förlorade", "drawdown", "tilt", "stressad", "fomo",
    "psychology", "discipline", "emotions", "lost", "losing", "tilt",
    "overtrading", "överhandel", "impuls", "impulse",
    # Risk
    "risk", "riskhantering", "lot size", "lotsize", "position size",
    "prop firm", "drawdown", "max loss", "daily loss", "consistency",
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


TONE_KEYWORDS = {
    "frustrated": [
        "frustrerad", "stress", "stressad", "arg", "besviken", "trött", "rädd", "förtvivlad",
        "jävla", "fuck", "idiot", "misslyckad", "förlorad", "förlust", "suck", "hopplös",
        "ger upp", "orkar inte", "fan", "helvete", "irriterad", "lost", "burned out",
        "done with this", "hate this", "not working", "frustrated", "annoyed",
    ],
    "overconfident": [
        "enkelt", "lätt", "given", "safe", "garanterat", "no risk", "maxade", "100%",
        "säker", "det här vinner", "oslagbar", "scoop", "take it", "självklart",
        "kan inte gå fel", "easy money", "obvious", "guaranteed", "cant lose",
        "crushing it", "on fire", "unstoppable", "printing money",
    ],
    "fearful": [
        "oroar", "orolig", "rädd", "feg", "fomo", "ångest", "nervös", "stressad",
        "tvekar", "osäker", "inte säker", "vet inte", "kanske", "ska jag",
        "afraid", "scared", "not sure", "uncertain", "hesitating", "worried",
        "missing out", "missar",
    ],
    "revenge": [
        "revenge", "ta igen", "ta tillbaka", "hämd", "illska", "sätta tillbaka",
        "komma tillbaka", "make up", "make it back", "win it back", "double down",
        "dubblar", "ökar", "last trade", "one more", "en till", "just en till",
        "sista trade", "ska ta igen",
    ],
    "high_risk": [
        "riskerar", "för mycket", "max risk", "stor lot", "lot size", "high risk",
        "överrisk", "överdrivet", "big lot", "max lot", "all in", "allt in",
        "bigger size", "increase risk", "ökar risk", "full risk",
    ],
    "early_entry": [
        "gick in tidigt", "lite tidigt", "innan engulfing", "innan bekräftelse",
        "tyckte det såg bra ut", "såg bra ut", "kändes rätt", "went in early",
        "early entry", "before confirmation", "jumped in",
    ],
    "system_doubt": [
        "systemet funkar inte", "indikatorn är fel", "strategin funkar inte",
        "ingen edge", "strategy doesn't work", "indicator wrong", "system broken",
        "the system", "quit trading", "slutar trада",
    ],
}


TONE_INSTRUCTIONS = {
    "frustrated": "The user is frustrated or burned out. Be calm, grounding, and process-focused. Use short sentences. Acknowledge the feeling first, then redirect to the next correct step. Don't lecture.",
    "overconfident": "The user is overconfident. Push back directly. Emphasize that 5 winning trades prove nothing. Challenge their assumptions. Ask what their exit plan is if they lose now. Don't validate the overconfidence.",
    "fearful": "The user is fearful or showing FOMO. Offer clear, structured guidance. Reduce complexity to one thing at a time. Remind them: no trade is the last trade. Ask: what does the setup checklist say?",
    "revenge": "CRITICAL: The user is showing revenge trading signals. Stop them immediately. Name the behavior directly — revenge trading destroys accounts in days. Ask how many times they've seen this pattern in themselves. Suggest closing the platform now.",
    "high_risk": "The user is discussing high risk or oversized positions. Hard stop on encouragement. Warn about risk limits. Ask: what does your risk management rule say? Remind them risk is not scaled until discipline is consistent.",
    "early_entry": "The user took or is considering an early entry without confirmation. Challenge this directly. Ask: why didn't you wait for the engulfing? Remind them early entry is retail logic, not smart money logic.",
    "system_doubt": "The user is doubting their system after losses. Separate system from execution — it's almost always execution. Ask: which specific checklist criterion wasn't met on the last losing trade? System works. Execution varies.",
    "neutral": "The user tone is neutral. Respond with clear, rational, rule-based feedback. Use the Socratic method when appropriate — ask one good question instead of giving all the answers.",
}


def detect_user_tone(user_text: str) -> tuple[str, str]:
    text_lower = user_text.lower()
    for tone, words in TONE_KEYWORDS.items():
        for word in words:
            if word in text_lower:
                return tone, TONE_INSTRUCTIONS[tone]
    return "neutral", TONE_INSTRUCTIONS["neutral"]


def parse_trade_note(note: str) -> dict:
    fields = {}
    if not note:
        return fields
    for part in note.split("|"):
        part = part.strip()
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key.strip().lower()] = value.strip()
        else:
            fields.setdefault("tags", []).append(part)
    return fields


def detect_trade_patterns(trades: list[dict]) -> str:
    if not trades:
        return ""

    repeated_sweep_missing = 0
    repeated_losses = 0
    lot_values = []
    time_stamps = []
    results = []
    sessions = []

    for trade in trades:
        note = trade.get("note", "")
        parsed = parse_trade_note(note)

        # Lot sizes
        lot = parsed.get("lot")
        if lot:
            try:
                lot_values.append(float(lot))
            except ValueError:
                pass

        # Sweep missing
        swept = parsed.get("swept", "").upper()
        if swept in ["MISSING", "NO", "NONE", ""]:
            repeated_sweep_missing += 1

        # Results
        result = trade.get("result", "").lower()
        if result in ["loss", "sl", "stopped out", "förlust", "-"]:
            repeated_losses += 1
        else:
            repeated_losses = 0  # reset on win

        # Timestamps
        timestamp = trade.get("timestamp")
        if timestamp:
            try:
                time_stamps.append(datetime.fromisoformat(timestamp))
            except Exception:
                pass

        # Sessions
        session = parsed.get("session", "").lower()
        if session:
            sessions.append(session)

    patterns = []

    # Sweep discipline
    if repeated_sweep_missing >= 3:
        patterns.append(
            f"PATTERN: Sweep missing på {repeated_sweep_missing} av de senaste trades. "
            "Du sänker din entry-standard. A+ kräver bekräftat sweep."
        )

    # Loss streak — trigger loss control protocol
    if repeated_losses >= 2:
        patterns.append(
            f"LOSS STREAK DETECTED: {repeated_losses} förluster i rad. "
            "Enligt WiseMind-regler ska trading stoppas vid 2 förluster. Fråga användaren om de fortfarande tradar."
        )
    if repeated_losses >= 3:
        patterns.append(
            "CRITICAL: 3 förluster i rad detekterade. 48 timmars tvångspaus är obligatorisk enligt systemreglerna."
        )

    # Overtrading
    trade_timestamps = sorted(time_stamps, reverse=True)
    if len(trade_timestamps) >= 3:
        now = trade_timestamps[0]
        within_24h = sum(1 for ts in trade_timestamps if (now - ts).total_seconds() <= 86400)
        if within_24h >= 4:
            patterns.append(
                f"OVERTRADING: {within_24h} trades på 24 timmar. Max är 2 trades per dag för A+ setups. "
                "Fråga vad som drev de extra tradesen."
            )
        elif within_24h >= 3:
            patterns.append(
                f"TRADE COUNT: {within_24h} trades senaste 24h — vid gränsen för dagsgräns. Påminn om max 2/dag."
            )

    # Lot spike — risk escalation
    if lot_values and len(lot_values) >= 2:
        avg_lot = sum(lot_values[1:]) / len(lot_values[1:])
        latest_lot = lot_values[0]
        if avg_lot > 0 and latest_lot > avg_lot * 2.5:
            patterns.append(
                f"RISK SPIKE: Senaste lot ({latest_lot:.2f}) är {latest_lot/avg_lot:.1f}x normen ({avg_lot:.2f}). "
                "Möjligt revenge trading eller feltänkt position sizing. Flagga direkt."
            )
        elif avg_lot > 0 and latest_lot > avg_lot * 1.75:
            patterns.append(
                f"LOT INCREASE: Senaste lot är {latest_lot/avg_lot:.1f}x genomsnittet. Kontrollera om risk-eskalering sker."
            )

    # Session pattern — trading outside killzones
    non_kz_sessions = [s for s in sessions if s not in ["london", "london+ext", "ny", "new york"]]
    if len(non_kz_sessions) >= 2:
        patterns.append(
            "OFF-KILLZONE TRADES detekterade. Trades utanför London/NY killzone har signifikant lägre edge. "
            "Fråga varför användaren inte väntade på killzone."
        )

    return " | ".join(patterns) if patterns else ""


def build_messages_for_claude(history: list, current_user_text: str, current_username: str) -> list:
    messages = []
    last_role = None
    for msg in history:
        role = msg["role"]
        username = msg["username"] or "okänd"
        text = msg["text"]
        if role == "user":
            content = f"[{username}]: {text}"
        else:
            content = text
        if role == last_role and messages:
            messages[-1]["content"] += f"\n{content}"
        else:
            messages.append({"role": role, "content": content})
            last_role = role
    current_content = f"[{current_username}]: {current_user_text}"
    if last_role == "user" and messages:
        messages[-1]["content"] += f"\n{current_content}"
    else:
        messages.append({"role": "user", "content": current_content})
    return messages


# ==================== CLAUDE RESPONSE ====================
async def claude_response(user_text: str, chat_id: int, username: str):
    try:
        model, reason = pick_model(user_text)
        clean_text = strip_force_prefix(user_text)
        tone_label, tone_description = detect_user_tone(clean_text)
        max_tokens = 800 if model == CLAUDE_MODEL_FAST else 1500
        history = await get_recent_messages(chat_id, limit=20)
        last_trade = await get_last_trade()
        recent_trades = await get_recent_trades(limit=10)
        trade_history_context = ""
        history_patterns = detect_trade_patterns(recent_trades)
        if history_patterns:
            trade_history_context = f"\n\nTrade history insight: {history_patterns}"
        alert_context = "\n\nTradingView alerts are integrated into this bot. Recent incoming signal alerts are stored and available as context for your analysis."
        trade_context = f"\n\nSenaste trade i systemet: {last_trade}" if last_trade else ""
        tone_context = f"\n\nUser tone: {tone_label}. {tone_description}"
        full_system = SYSTEM_PROMPT + alert_context + trade_context + tone_context + trade_history_context
        messages = build_messages_for_claude(history, clean_text, username)
        logger.info(f"Routing → {model.split('-')[1].upper()} ({reason}) | tone={tone_label} | history={len(history)} msgs | input_len={len(clean_text)}")
        start = time.time()
        response = await claude.messages.create(
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
            text = f"📊 *Senaste trade*\n{trade.get('symbol')} {trade.get('direction', '').upper()} @ {trade.get('entry')}\n_{trade.get('note', '')}_"
        else:
            text = "📭 Inga trades än."
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"/last command failed: {e}")
        await update.message.reply_text("⚠️ Kunde inte hämta senaste trade.")


async def cmd_clear_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/clearmemory from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        await cleanup_old_messages(update.effective_chat.id, keep_last=0)
        await update.message.reply_text("🧹 Konversationsminne rensat för denna chat.")
    except Exception as e:
        logger.error(f"/clearmemory failed: {e}")
        await update.message.reply_text("⚠️ Kunde inte rensa minnet.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username or "okänd"
    text = update.message.text
    text_lower = text.lower()
    try:
        await save_message(chat_id, user_id, username, "user", text)
    except Exception as e:
        logger.error(f"Failed to save message: {e}")
    if "@wisefx_bot" in text_lower or "wisemind" in text_lower:
        logger.info(f"Bot tagged by {username} ({user_id}) in chat {chat_id}: {text[:80]}")
        signal_evaluation = None
        signal_data = extract_signal_data_from_text(text)
        if signal_data:
            signal_evaluation = evaluate_signal(signal_data)
            logger.info(f"Signal evaluation from user text: {signal_evaluation}")
        try:
            claude_text = text
            if signal_evaluation:
                claude_text += f"\n\n[Signal Evaluation: {signal_evaluation['explanation']}]"
            response = await claude_response(claude_text, chat_id, username)
            await update.message.reply_text(response)
            try:
                await save_message(chat_id, None, "WiseMind AI", "assistant", response)
            except Exception as e:
                logger.error(f"Failed to save bot reply: {e}")
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


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.first_name or update.effective_user.username or "okänd"
    message = update.message
    file_obj = None
    filename = None
    mime_type = None

    if message.photo:
        file_obj = await message.photo[-1].get_file()
        filename = f"{username}_photo_{message.photo[-1].file_unique_id}.jpg"
        mime_type = "image/jpeg"
    elif message.document:
        document = message.document
        file_obj = await document.get_file()
        filename = document.file_name or f"{username}_document"
        mime_type = document.mime_type
    else:
        return

    if not file_obj or not filename:
        return

    caption_text = message.caption or ""
    filename = sanitize_filename(filename)

    try:
        local_path = await download_telegram_file(file_obj, filename)
        extracted_text = ""
        if is_image_file(filename, mime_type):
            extracted_text = extract_text_from_image(local_path)
        elif is_text_file(filename, mime_type):
            extracted_text = extract_text_from_document(local_path)

        if caption_text:
            await save_message(chat_id, user_id, username, "user", f"Uploaded file: {filename} with caption: {caption_text}")
        else:
            await save_message(chat_id, user_id, username, "user", f"Uploaded file: {filename}")

        if extracted_text:
            await save_message(chat_id, user_id, username, "user", f"Extracted text from {filename}:\n{extracted_text}")

        signal_evaluation = None
        if extracted_text:
            signal_data = extract_signal_data_from_text(extracted_text)
            if signal_data:
                signal_evaluation = evaluate_signal(signal_data)
                logger.info(f"Signal evaluation from screenshot: {signal_evaluation}")

        if extracted_text:
            prompt = (
                "User uploaded a screenshot or trade file and wants feedback on the setup. "
                "Use the extracted trade details and analyze the entry, SL, TP, risk management, and whether the setup matches WiseMind rules.\n\n"
                f"Extracted content:\n{extracted_text}"
            )
            if caption_text:
                prompt += f"\n\nImage caption:\n{caption_text}"
            if signal_evaluation:
                prompt += f"\n\nSignal Evaluation: {signal_evaluation['explanation']}"
        else:
            prompt = (
                "User uploaded a screenshot or trade file but no text could be extracted automatically. "
                "If there is a caption or description, use it to help infer the trade setup. "
                "Otherwise ask for the exact trade details and suggest what to include: pair, timeframe, session, levels, entry, SL, TP, risk %.\n\n"
            )
            if caption_text:
                prompt += f"Caption:\n{caption_text}"

        response = await claude_response(prompt, chat_id, username)
        await update.message.reply_text(response)
        await save_message(chat_id, None, "WiseMind AI", "assistant", response)
        try:
            await cleanup_old_messages(chat_id, keep_last=100)
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    except Exception as e:
        logger.error(f"Failed to process media upload: {e}")
        await update.message.reply_text(
            "⚠️ Kunde inte processa filen just nu. Skicka en tydlig screenshot eller exportera tradeinformationen som text."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)


# ==================== UNIFIED ASYNC STARTUP ====================
async def run_bot_and_webhook():
    """Run Telegram bot and FastAPI webhook on the same asyncio event loop."""
    # 1. Initialize database
    logger.info("=" * 60)
    logger.info("🚀 WiseMind AI starting...")
    logger.info("=" * 60)
    await init_db()
    logger.info("✅ Database initialized (conversation memory + trades)")

    # 2. Build Telegram bot application
    bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CommandHandler("last", cmd_last))
    bot_app.add_handler(CommandHandler("clearmemory", cmd_clear_memory))
    bot_app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_error_handler(error_handler)
    logger.info("✅ Telegram bot handlers registered")

    # 3. Configure uvicorn server (programmatic, NOT uvicorn.run)
    uvicorn_config = uvicorn.Config(
        webhook_app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info",
        access_log=True,
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    logger.info(f"✅ Webhook configured: http://0.0.0.0:{WEBHOOK_PORT}/webhook")
    logger.info(f"   PORT env var resolved to: {WEBHOOK_PORT}")

    # 4. Start Telegram bot (must initialize before run)
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ Telegram bot polling started")

    # 5. Run uvicorn forever (this blocks until shutdown)
    logger.info("🌐 Webhook server starting (uvicorn.serve)...")
    logger.info("=" * 60)
    logger.info("🎯 WiseMind AI is LIVE — listening for TradingView webhooks + Telegram messages")
    logger.info("=" * 60)
    try:
        await uvicorn_server.serve()
    finally:
        logger.info("Shutdown signal received — stopping bot and webhook...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        logger.info("Clean shutdown complete.")


def main():
    """Entry point. Runs the unified async server."""
    try:
        asyncio.run(run_bot_and_webhook())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error in main: {type(e).__name__}: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

