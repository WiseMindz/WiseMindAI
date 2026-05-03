"""
Webhook handler för TradingView-alerts.
Tar emot JSON från Pine Script v9.17+, sparar i DB, postar till Telegram.

v9.17 schema includes deep signal data fields:
- displacement_atr, engulf_body_pct, vol_spike, htf_aligned
"""

import logging
from fastapi import FastAPI, Request, HTTPException
from typing import Optional
import re
from telegram import Bot
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_SECRET,
    ACCOUNT_BALANCE,
    ACCOUNT_RISK_PERCENT,
)
from database import save_trade, save_message
from signal_utils import evaluate_signal

logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="WiseMind Webhook Receiver")

# Telegram bot för att posta meddelanden
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)


# ==================== PIP VALUE LOOKUP ====================
PIP_VALUE_USD = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCHF": 10.5, "USDJPY": 9.5, "USDCAD": 7.3,
    "XAUUSD": 10.0, "XAGUSD": 50.0,
}

PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCHF": 0.0001, "USDJPY": 0.01, "USDCAD": 0.0001,
    "XAUUSD": 0.10, "XAGUSD": 0.001,
}


def get_pip_value(symbol: str) -> float:
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return PIP_VALUE_USD.get(clean, 10.0)


def get_pip_size(symbol: str) -> float:
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return PIP_SIZE.get(clean, 0.0001)


def calculate_lot_size(symbol: str, entry: float, sl: float, balance: float, risk_pct: float) -> dict:
    risk_dollars = balance * (risk_pct / 100.0)
    sl_distance_price = abs(entry - sl)
    pip_size = get_pip_size(symbol)
    sl_pips = sl_distance_price / pip_size
    pip_value = get_pip_value(symbol)

    if sl_pips == 0 or pip_value == 0:
        return {"lot": 0, "risk_dollars": risk_dollars, "sl_pips": 0, "pip_value": pip_value}

    lot = risk_dollars / (sl_pips * pip_value)
    lot = round(lot, 2)

    return {
        "lot": lot,
        "risk_dollars": round(risk_dollars, 2),
        "sl_pips": round(sl_pips, 1),
        "pip_value": pip_value,
    }


def calculate_tp_profit(symbol: str, entry: float, tp: float, lot: float) -> float:
    distance_price = abs(tp - entry)
    pip_size = get_pip_size(symbol)
    tp_pips = distance_price / pip_size
    pip_value = get_pip_value(symbol)
    return round(tp_pips * pip_value * lot, 2)


def parse_tradingview_alert(alert_text: str) -> dict:
    """Försök extrahera trade-data från TradingView alert text (legacy fallback)."""
    lines = [line.strip() for line in alert_text.splitlines() if line.strip()]
    parsed = {}

    if lines:
        header = lines[0]
        header_match = re.search(r"\b([A-Z]{3,6}(?:USD|EUR|JPY|GBP|CHF|AUD|CAD|NZD))\b", header)
        if header_match:
            parsed["symbol"] = header_match.group(1)

        trade_match = re.search(r"\b(T\d+\s*\([^)]*\)|T\d+|\w+\s*\([^)]*\))\b", header)
        if trade_match:
            parsed["trade"] = trade_match.group(1)

        session_match = re.search(r"\[([^\]]+)\]", header)
        if session_match:
            parsed["session"] = session_match.group(1)
            rest = header[session_match.end():].strip()
            profile_match = re.search(r"\[([^\]]+)\]", rest)
            if profile_match:
                parsed["profile"] = profile_match.group(1)

    def extract_value(pattern, text):
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else None

    for line in lines:
        if re.match(r"^Entry", line, re.IGNORECASE):
            parsed["entry"] = float(extract_value(r"Entry\s*[:=]?\s*([0-9]+\.?[0-9]*)", line) or 0)
        elif re.match(r"^SL", line, re.IGNORECASE):
            parsed["sl"] = float(extract_value(r"SL\s*[:=]?\s*([0-9]+\.?[0-9]*)", line) or 0)
            parsed["sl_source"] = extract_value(r"SL\s*[:=]?.*?\(([^)]+)\)", line) or ""
        elif re.match(r"^TP", line, re.IGNORECASE):
            parsed["tp"] = float(extract_value(r"TP\s*[:=]?\s*([0-9]+\.?[0-9]*)", line) or 0)
            parsed["tp_source"] = extract_value(r"@([A-Za-z0-9_]+)", line) or ""
            rr_value = extract_value(r"\(([0-9]+\.?[0-9]*)R\)", line)
            if rr_value:
                parsed["rr"] = float(rr_value)
        elif re.match(r"^Lot", line, re.IGNORECASE):
            parsed["lot"] = float(extract_value(r"Lot\s*[:=]?\s*([0-9]+\.?[0-9]*)", line) or 0)
        elif re.match(r"^Swept", line, re.IGNORECASE):
            parsed["swept"] = extract_value(r"Swept\s*[:=]?\s*(.+)$", line) or ""
        elif re.search(r"asia", line, re.IGNORECASE):
            parsed["asia_wide"] = True

        if not parsed.get("side"):
            side_match = re.search(r"\b(LONG|SHORT)\b", line, re.IGNORECASE)
            if side_match:
                parsed["side"] = side_match.group(1).upper()

    if "symbol" not in parsed:
        symbol_match = re.search(r"\b([A-Z]{3,6}(?:USD|EUR|JPY|GBP|CHF|AUD|CAD|NZD))\b", alert_text)
        if symbol_match:
            parsed["symbol"] = symbol_match.group(1)
    if "side" not in parsed:
        side_match = re.search(r"\b(LONG|SHORT)\b", alert_text, re.IGNORECASE)
        if side_match:
            parsed["side"] = side_match.group(1).upper()
    if "entry" not in parsed or "sl" not in parsed or "tp" not in parsed:
        for field in ["entry", "sl", "tp", "rr"]:
            if field not in parsed:
                value = extract_value(rf"\b{field}\b\s*[:=]?\s*([0-9]+\.?[0-9]*)", alert_text)
                if value:
                    parsed[field] = float(value)

    return parsed


# ==================== MESSAGE FORMATTING ====================

def get_chart_url(symbol: str) -> str:
    """Bygger TradingView chart-länk för en symbol."""
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return f"https://www.tradingview.com/chart/?symbol={clean}"


def format_telegram_message(data: dict, lot_calc: dict, tp_profit: float, evaluation: dict) -> str:
    """Bygger ett snyggt formatterat Telegram-meddelande från alert data + signal evaluation."""
    side = data.get("side", "?").upper()
    arrow = "▲" if side == "LONG" else "▼"
    symbol = data.get("symbol", "?")
    trade_type = data.get("trade", "")
    session = data.get("session", "")
    profile = data.get("profile", "")
    entry = data.get("entry", 0)
    sl = data.get("sl", 0)
    tp = data.get("tp", 0)
    rr = data.get("rr", 0)
    sl_src = data.get("sl_source", "")
    tp_src = data.get("tp_source", "")
    swept = data.get("swept", "")
    after_manip = data.get("after_manipulation", False)
    asia_wide = data.get("asia_wide", False)
    htf_aligned = data.get("htf_aligned", False)

    profile_tag = f" [{profile}]" if profile else ""
    session_tag = f" [{session}]" if session else ""
    trade_tag = f" {trade_type}" if trade_type else ""
    tp_source_tag = f" @{tp_src}" if tp_src else ""
    sl_source_tag = f"{sl_src}" if sl_src else ""
    sl_source_has_pips = "pips" in sl_src.lower() if sl_src else False
    rr_tag = f" ({rr}R)" if rr else ""

    msg = f"<b>{arrow} {symbol}{trade_tag}{session_tag}{profile_tag}</b>\n"
    msg += f"Entry: <b>{entry}</b>\n"
    msg += f"SL: <b>{sl}</b>"
    if sl_source_tag or lot_calc.get("sl_pips"):
        msg += " ("
        if sl_source_tag:
            msg += sl_source_tag
            if lot_calc.get("sl_pips") and not sl_source_has_pips:
                msg += ", "
        if lot_calc.get("sl_pips") and not sl_source_has_pips:
            msg += f"{lot_calc['sl_pips']} pips"
        msg += ")"
    msg += "\n"
    msg += f"TP: <b>{tp}</b>{tp_source_tag}{rr_tag}\n\n"
    msg += f"💰 Lot: <b>{lot_calc['lot']}</b> | Risk: ${lot_calc['risk_dollars']} | TP profit: ${tp_profit}\n"

    flags = []
    if swept:
        flags.append(f"Swept: {swept}")
    if after_manip:
        flags.append("✓ AFTER MANIPULATION")
    if htf_aligned:
        flags.append("✓ HTF ALIGNED")
    if asia_wide:
        flags.append("⚠ ASIA WIDE")
    if flags:
        msg += "\n".join(flags) + "\n"

    rating = evaluation.get("rating", "?")
    score = evaluation.get("score", 0)
    rating_emoji = "🟢" if rating == "A+" else ("🟡" if rating == "B" else "🔴")
    msg += f"\n🧠 <b>Signal Quality:</b> {rating_emoji} <b>{rating}</b> ({score}/10)\n"

    reasons = evaluation.get("reasons", [])[:5]
    if reasons:
        msg += "<i>" + " | ".join(reasons) + "</i>\n"

    chart_url = get_chart_url(symbol)
    msg += f"\n📊 <a href=\"{chart_url}\">View Chart on TradingView</a>"
    msg += "\n💾 <i>Sparat i databas</i>"

    return msg


# ==================== WEBHOOK ENDPOINT ====================

@app.get("/")
async def root():
    return {"status": "WiseMind Webhook Receiver är igång", "version": "9.17"}


@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()

        if not all(field in data for field in ["symbol", "side", "entry", "sl", "tp"]):
            alert_text = data.get("alert_message") or data.get("message") or data.get("text")
            if isinstance(alert_text, str):
                parsed = parse_tradingview_alert(alert_text)
                logger.info(f"Parsed alert text into fields: {parsed}")
                data = {**parsed, **data}

        logger.info(f"Webhook received: {data.get('symbol')} {data.get('side')} {data.get('trade')}")

        if data.get("secret") != WEBHOOK_SECRET:
            logger.warning(f"Webhook secret mismatch! Got: {data.get('secret')}")
            raise HTTPException(status_code=401, detail="Invalid secret")

        required = ["symbol", "side", "entry", "sl", "tp"]
        for field in required:
            if field not in data:
                logger.error(f"Webhook missing field: {field}")
                raise HTTPException(status_code=400, detail=f"Missing field: {field}")

        lot_calc = calculate_lot_size(
            symbol=data["symbol"],
            entry=float(data["entry"]),
            sl=float(data["sl"]),
            balance=ACCOUNT_BALANCE,
            risk_pct=ACCOUNT_RISK_PERCENT,
        )

        tp_profit = calculate_tp_profit(
            symbol=data["symbol"],
            entry=float(data["entry"]),
            tp=float(data["tp"]),
            lot=lot_calc["lot"],
        )

        evaluation = evaluate_signal(data)
        logger.info(f"Signal evaluation: {evaluation['rating']} ({evaluation['score']}/10)")

        try:
            note = (
                f"{data.get('trade', '')} | {data.get('session', '')} | RR:{data.get('rr', 0)} | Lot:{lot_calc['lot']} | "
                f"Swept:{data.get('swept', '')} | DispATR:{data.get('displacement_atr', 0)} | "
                f"EngulfPct:{data.get('engulf_body_pct', 0)} | VolSpike:{data.get('vol_spike', 0)} | "
                f"HTF:{data.get('htf_aligned', False)} | AfterManip:{data.get('after_manipulation', False)} | "
                f"AsiaWide:{data.get('asia_wide', False)} | TF:{data.get('tf', '')} | "
                f"Rating:{evaluation['rating']} | Score:{evaluation['score']}/10"
            )
            await save_trade(
                symbol=data["symbol"],
                direction=data["side"].lower(),
                entry=float(data["entry"]),
                note=note,
            )
            logger.info("Trade saved to database")
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")

        msg = format_telegram_message(data, lot_calc, tp_profit, evaluation)

        # Broadcast to private + public groups
        BROADCAST_TARGETS = [TELEGRAM_CHAT_ID, -5179097995]
        BROADCAST_TARGETS = list(dict.fromkeys(BROADCAST_TARGETS))  # dedupe

        post_results = []
        for target_chat_id in BROADCAST_TARGETS:
            try:
                await telegram_bot.send_message(
                    chat_id=target_chat_id,
                    text=msg,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )
                post_results.append({"chat_id": target_chat_id, "status": "ok"})
                logger.info(f"Posted to Telegram chat_id={target_chat_id}")
            except Exception as e:
                post_results.append({"chat_id": target_chat_id, "status": f"error: {e}"})
                logger.error(f"Failed to post to chat_id={target_chat_id}: {e}")

        # Save alert to PRIMARY chat memory only (Claude context)
        try:
            alert_summary = (
                f"TradingView alert received: {data.get('symbol')} {data.get('side')} {data.get('trade')} "
                f"entry={data.get('entry')} sl={data.get('sl')} tp={data.get('tp')} rr={data.get('rr')} "
                f"rating={evaluation['rating']} score={evaluation['score']}/10"
            )
            await save_message(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=None,
                username="TradingView",
                role="system",
                text=alert_summary,
            )
        except Exception as e:
            logger.error(f"Failed to save alert summary: {e}")

        # If ALL chats failed, escalate
        if all(r["status"].startswith("error") for r in post_results):
            raise HTTPException(status_code=500, detail=f"All Telegram broadcasts failed: {post_results}")

        return {
            "status": "ok",
            "lot": lot_calc["lot"],
            "risk_dollars": lot_calc["risk_dollars"],
            "tp_profit": tp_profit,
            "rating": evaluation["rating"],
            "score": evaluation["score"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/test")
async def test_endpoint():
    """Test-endpoint för att verifiera Telegram broadcast i ALLA grupper."""
    BROADCAST_TARGETS = [TELEGRAM_CHAT_ID, -5179097995]
    BROADCAST_TARGETS = list(dict.fromkeys(BROADCAST_TARGETS))

    results = []
    for target_chat_id in BROADCAST_TARGETS:
        try:
            await telegram_bot.send_message(
                chat_id=target_chat_id,
                text=f"✅ <b>Webhook test</b>\nWiseMind webhook receiver fungerar (v9.17)!\nThis chat_id: <code>{target_chat_id}</code>",
                parse_mode="HTML",
            )
            results.append({"chat_id": target_chat_id, "status": "ok"})
        except Exception as e:
            results.append({"chat_id": target_chat_id, "status": f"error: {e}"})
            logger.error(f"Test failed for chat_id={target_chat_id}: {e}")
    return {"status": "Test broadcast complete", "results": results}
