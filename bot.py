import asyncio
import logging
import time
import threading
from datetime import datetime
import uvicorn
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
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


TONE_KEYWORDS = {
    "frustrated": ["frustrerad", "stress", "stressad", "arg", "besviken", "trött", "rädd", "förtvivlad", "jävla", "fuck", "idiot", "misslyckad", "förlorad", "förlust", "suck"],
    "overconfident": ["enkelt", "lätt", "given", "safe", "garanterat", "no risk", "maxade", "100%", "säker", "det här vinner", "oslagbar", "scoop", "take it"],
    "fearful": ["oroar", "orolig", "rädd", "feg", "fomo", "ångest", "nervös", "stressad", "tvekar", "osäker"],
    "revenge": ["revenge", "ta igen", "ta tillbaka", "hämd", "illska", "sätta tillbaka", "komma tillbaka", "make up"],
    "high_risk": ["riskerar", "för mycket", "max risk", "stor lot", "lot size", "high risk", "överrisk", "överdrivet"],
}


TONE_INSTRUCTIONS = {
    "frustrated": "The user is frustrated or burned out. Be calm, supportive, and process-focused. Reinforce discipline and help them refocus on the next correct step.",
    "overconfident": "The user is overconfident. Push back gently, emphasize the system rules, and warn against taking unnecessary risk or impulsive trades.",
    "fearful": "The user is fearful or uncertain. Offer clear guidance, reduce complexity, and remind them to trade only when the setup fits the rules.",
    "revenge": "The user is showing revenge or ego-driven language. Challenge this behavior directly and remind them that revenge trading is the fastest way to lose.",
    "high_risk": "The user is talking about high risk or large position size. Warn about risk limits and force them back to proper risk management.",
    "neutral": "The user tone is neutral. Respond with clear, rational, and rule-based feedback.",
}


def detect_user_tone(user_text: str) -> tuple[str, str]:
    text_lower = user_text.lower()
    best_match = "neutral"
    for tone, words in TONE_KEYWORDS.items():
        for word in words:
            if word in text_lower:
                best_match = tone
                return best_match, TONE_INSTRUCTIONS[tone]
    return best_match, TONE_INSTRUCTIONS[best_match]


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
    total_trades = len(trades)
    lot_values = []
    time_stamps = []
    sweep_miss_trades = []

    for trade in trades:
        note = trade.get("note", "")
        parsed = parse_trade_note(note)
        lot = parsed.get("lot")
        if lot:
            try:
                lot_values.append(float(lot))
            except ValueError:
                pass
        swept = parsed.get("swept", "").upper()
        if swept in ["MISSING", "NO", "NONE", ""]:
            repeated_sweep_missing += 1
            sweep_miss_trades.append(trade)
        timestamp = trade.get("timestamp")
        if timestamp:
            try:
                time_stamps.append(datetime.fromisoformat(timestamp))
            except Exception:
                pass

    patterns = []
    if repeated_sweep_missing >= 3:
        patterns.append("Det här liknar dina senaste 3 trades där du inte hade sweep.")

    if len(trade_timestamps := sorted(time_stamps, reverse=True)) >= 3:
        now = trade_timestamps[0]
        within_24h = sum(1 for ts in trade_timestamps if (now - ts).total_seconds() <= 86400)
        if within_24h >= 3:
            patterns.append("Du har tagit många trades på kort tid. Det kan vara överhandel.")

    if lot_values:
        avg_lot = sum(lot_values) / len(lot_values)
        latest_lot = lot_values[0]
        if avg_lot > 0 and latest_lot > avg_lot * 2:
            patterns.append("Din senaste lot size avviker kraftigt från din norm. Kontrollera riskhanteringen.")

    return " ".join(patterns)


def evaluate_signal(signal_data: dict) -> dict:
    """
    Evaluerar en signal mot WiseMind-regler och ger score/rating.

    Args:
        signal_data: dict med signalinformation (från webhook, OCR, etc.)

    Returns:
        dict med score (0-10), rating (A+/B/C), förklaring
    """
    score = 0
    reasons = []

    # 1. Sweep (2 poäng)
    swept = signal_data.get("swept", "").strip().upper()
    if swept and swept not in ["MISSING", "NO", "NONE", ""]:
        score += 2
        reasons.append("Sweep: ✓")
    else:
        reasons.append("Sweep: ✗ (Saknas)")

    # 2. Displacement (2 poäng)
    displacement = signal_data.get("displacement", "").strip().lower()
    if displacement in ["yes", "true", "1"]:
        score += 2
        reasons.append("Displacement: ✓")
    else:
        reasons.append("Displacement: ✗ (Saknas)")

    # 3. PD-zone touch (2 poäng)
    pd_zone = signal_data.get("pd_zone", "").strip().upper()
    if pd_zone and pd_zone not in ["MISSING", "NO", "NONE", ""]:
        score += 2
        reasons.append("PD-zone touch: ✓")
    else:
        reasons.append("PD-zone touch: ✗ (Saknas)")

    # 4. Engulfing (2 poäng)
    engulfing = signal_data.get("engulfing", "").strip().lower()
    if engulfing in ["yes", "true", "1"]:
        score += 2
        reasons.append("Engulfing: ✓")
    else:
        reasons.append("Engulfing: ✗ (Saknas)")

    # 5. Session-regler (2 poäng)
    session = signal_data.get("session", "").strip().lower()
    tf = signal_data.get("tf", "").strip().lower()
    valid_sessions = ["london", "ny", "asia"]
    valid_tf = ["5m", "1m"]
    if session in valid_sessions and tf in valid_tf:
        score += 2
        reasons.append("Session/TF: ✓")
    else:
        reasons.append("Session/TF: ✗ (Ogiltig session eller TF)")

    # Bonus: RR (1 poäng, max total 10)
    rr = signal_data.get("rr", 0)
    if rr >= 3:
        score += min(1, 10 - score)  # Max 10 total
        reasons.append("RR: ✓ (≥3:1)")
    elif rr >= 2:
        score += min(0.5, 10 - score)
        reasons.append("RR: ~ (≥2:1)")
    else:
        reasons.append("RR: ✗ (<2:1)")

    # Rating baserat på score
    if score >= 8:
        rating = "A+"
    elif score >= 6:
        rating = "B"
    else:
        rating = "C"

    explanation = f"Score: {score}/10 ({rating}). " + " | ".join(reasons)

    return {
        "score": score,
        "rating": rating,
        "explanation": explanation
    }


def extract_signal_data_from_text(text: str) -> dict:
    """
    Försöker extrahera signaldata från fri text (OCR eller användarinput).

    Args:
        text: fri text att analysera

    Returns:
        dict med extraherade signaldata
    """
    data = {}
    text_lower = text.lower()

    # Symbol
    import re
    symbol_match = re.search(r'\b([a-z]{3,6}(?:usd|eur|jpy|gbp|chf|aud|cad|nzd))\b', text_lower)
    if symbol_match:
        data["symbol"] = symbol_match.group(1).upper()

    # Side
    if "long" in text_lower:
        data["side"] = "LONG"
    elif "short" in text_lower:
        data["side"] = "SHORT"

    # Entry/SL/TP
    entry_match = re.search(r'entry[:=]?\s*([0-9]+\.?[0-9]*)', text_lower)
    if entry_match:
        data["entry"] = float(entry_match.group(1))

    sl_match = re.search(r'sl[:=]?\s*([0-9]+\.?[0-9]*)', text_lower)
    if sl_match:
        data["sl"] = float(sl_match.group(1))

    tp_match = re.search(r'tp[:=]?\s*([0-9]+\.?[0-9]*)', text_lower)
    if tp_match:
        data["tp"] = float(tp_match.group(1))

    # RR
    rr_match = re.search(r'rr[:=]?\s*([0-9]+\.?[0-9]*)', text_lower)
    if rr_match:
        data["rr"] = float(rr_match.group(1))

    # Swept
    if "swept" in text_lower or "sweep" in text_lower:
        data["swept"] = "YES"

    # Displacement
    if "displacement" in text_lower or "atr" in text_lower:
        data["displacement"] = "yes"

    # PD zone
    if "pd" in text_lower or "fvg" in text_lower or "ob" in text_lower:
        data["pd_zone"] = "YES"

    # Engulfing
    if "engulf" in text_lower:
        data["engulfing"] = "yes"

    # Session
    if "london" in text_lower:
        data["session"] = "London"
    elif "ny" in text_lower or "new york" in text_lower:
        data["session"] = "NY"
    elif "asia" in text_lower:
        data["session"] = "Asia"

    # TF
    if "5m" in text_lower:
        data["tf"] = "5m"
    elif "1m" in text_lower:
        data["tf"] = "1m"

    return data


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

        # Försök extrahera och evaluera signal från användartext
        signal_evaluation = None
        signal_data = extract_signal_data_from_text(text)
        if signal_data:
            signal_evaluation = evaluate_signal(signal_data)
            logger.info(f"Signal evaluation from user text: {signal_evaluation}")

        try:
            # Modifiera text för Claude om vi har signaldata
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

        # Försök extrahera och evaluera signal från extracted text
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


# ==================== WEBHOOK SERVER (KÖR I BAKGRUND) ====================
def start_webhook_server():
    """Starta FastAPI webhook-servern i en separat thread."""
    logger.info(f"Starting webhook server on port {WEBHOOK_PORT}")
    uvicorn.run(
        webhook_app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="warning",
    )


# ==================== START ====================
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(init_db())
        logger.info("Database initialized (with conversation memory + trades)")

        # Starta webhook-server i bakgrundsthread
        webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
        webhook_thread.start()
        logger.info(f"✅ Webhook listening on http://0.0.0.0:{WEBHOOK_PORT}/webhook")

        # Starta Telegram-bot i huvudthread
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("last", cmd_last))
        app.add_handler(CommandHandler("clearmemory", cmd_clear_memory))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_error_handler(error_handler)

        logger.info("WiseMind AI starting... (Telegram bot + Webhook receiver)")
        logger.info("Try: @Wisefx_bot hej")

        app.run_polling(drop_pending_updates=True)

    finally:
        loop.close()


if __name__ == "__main__":
    main()

