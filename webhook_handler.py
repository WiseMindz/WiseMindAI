"""
Webhook handler för TradingView-alerts.
Tar emot JSON från Pine Script v9.15+, sparar i DB, postar till Telegram.
"""

import json
import logging
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
import re
from telegram import Bot
from anthropic import Anthropic
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_SECRET,
    ACCOUNT_BALANCE,
    ACCOUNT_RISK_PERCENT,
)
from database import save_trade, save_message

logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="WiseMind Webhook Receiver")

# Telegram bot för att posta meddelanden
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)


# ==================== PIP VALUE LOOKUP ====================
# Pip-värde per standard-lot per symbol (i USD)
# Detta används för lot size-beräkning
PIP_VALUE_USD = {
    "EURUSD": 10.0,    # 1 lot = 100,000 EUR, 1 pip = $10
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCHF": 10.5,
    "USDJPY": 9.5,
    "USDCAD": 7.3,
    "XAUUSD": 10.0,    # 1 lot = 100 oz, 1 pip ($0.10) = $10
    "XAGUSD": 50.0,
}

# Pip size (minsta prisrörelse) per symbol
PIP_SIZE = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "AUDUSD": 0.0001,
    "NZDUSD": 0.0001,
    "USDCHF": 0.0001,
    "USDJPY": 0.01,
    "USDCAD": 0.0001,
    "XAUUSD": 0.10,
    "XAGUSD": 0.001,
}


def get_pip_value(symbol: str) -> float:
    """Returnera pip-värde i USD per standard-lot."""
    # Normalisera (ta bort suffix som .x, _, etc.)
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return PIP_VALUE_USD.get(clean, 10.0)  # default $10/pip


def get_pip_size(symbol: str) -> float:
    """Returnera pip-storlek (smallest price unit)."""
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return PIP_SIZE.get(clean, 0.0001)


def calculate_lot_size(symbol: str, entry: float, sl: float, balance: float, risk_pct: float) -> dict:
    """
    Beräknar lot size baserat på account balance, risk %, och SL-distans.

    Returns:
        dict med lot, risk_dollars, sl_pips, pip_value_used
    """
    risk_dollars = balance * (risk_pct / 100.0)
    sl_distance_price = abs(entry - sl)
    pip_size = get_pip_size(symbol)
    sl_pips = sl_distance_price / pip_size
    pip_value = get_pip_value(symbol)

    if sl_pips == 0 or pip_value == 0:
        return {"lot": 0, "risk_dollars": risk_dollars, "sl_pips": 0, "pip_value": pip_value}

    # Lot size = risk_dollars / (sl_pips × pip_value_per_lot)
    lot = risk_dollars / (sl_pips * pip_value)
    lot = round(lot, 2)  # mikro-lot precision

    return {
        "lot": lot,
        "risk_dollars": round(risk_dollars, 2),
        "sl_pips": round(sl_pips, 1),
        "pip_value": pip_value,
    }


def calculate_tp_profit(symbol: str, entry: float, tp: float, lot: float) -> float:
    """Beräknar dollar-profit om TP träffas."""
    distance_price = abs(tp - entry)
    pip_size = get_pip_size(symbol)
    tp_pips = distance_price / pip_size
    pip_value = get_pip_value(symbol)
    return round(tp_pips * pip_value * lot, 2)


def parse_tradingview_alert(alert_text: str) -> dict:
    """Försök extrahera trade-data från TradingView alert text."""
    lines = [line.strip() for line in alert_text.splitlines() if line.strip()]
    parsed = {}

    if lines:
        header = lines[0]
        # exempel: EURUSD T1 (1st) [London] [EUR]
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

    # Fallbacks from inline text
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
def format_telegram_message(data: dict, lot_calc: dict, tp_profit: float) -> str:
    """Bygger ett snyggt formatterat Telegram-meddelande från alert data."""
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

    profile_tag = f" [{profile}]" if profile else ""
    session_tag = f" [{session}]" if session else ""
    trade_tag = f" {trade_type}" if trade_type else ""
    tp_source_tag = f" @{tp_src}" if tp_src else ""
    sl_source_tag = f"{sl_src}" if sl_src else ""
    sl_source_has_pips = "pips" in sl_src.lower()
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

    if swept:
        msg += f"Swept: {swept}\n"
    if after_manip:
        msg += "✓ AFTER MANIPULATION\n"
    if asia_wide:
        msg += "⚠ ASIA WIDE\n"

    msg += "\n📊 <i>Sparat i databas</i>"
    return msg


# ==================== WEBHOOK ENDPOINT ====================
@app.get("/")
async def root():
    """Health check — visa att webhook lever."""
    return {"status": "WiseMind Webhook Receiver är igång", "version": "1.0"}


@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Tar emot TradingView alert som JSON.
    Förväntat format (från Pine v9.15):
    {
        "secret": "wisemind2026",
        "symbol": "EURUSD",
        "side": "LONG",
        "trade": "T1 (1st)",
        "session": "London",
        "profile": "EUR",
        "entry": 1.16920,
        "sl": 1.16860,
        "sl_source": "engulf",
        "tp": 1.17430,
        "tp_source": "PDH",
        "rr": 5.0,
        "swept": "AL",
        "after_manipulation": false,
        "asia_wide": false,
        "tf": "5m"
    }
    """
    try:
        data = await request.json()

        # Försök läsa in data från TradingView alert-message om vanliga fält saknas
        if not all(field in data for field in ["symbol", "side", "entry", "sl", "tp"]):
            alert_text = data.get("alert_message") or data.get("message") or data.get("text")
            if isinstance(alert_text, str):
                parsed = parse_tradingview_alert(alert_text)
                logger.info(f"Parsed alert text into fields: {parsed}")
                data = {**parsed, **data}

        logger.info(f"Webhook received: {data.get('symbol')} {data.get('side')} {data.get('trade')}")

        # Verifiera secret
        if data.get("secret") != WEBHOOK_SECRET:
            logger.warning(f"Webhook secret mismatch! Got: {data.get('secret')}")
            raise HTTPException(status_code=401, detail="Invalid secret")

        # Validera nödvändiga fält
        required = ["symbol", "side", "entry", "sl", "tp"]
        for field in required:
            if field not in data:
                logger.error(f"Webhook missing field: {field}")
                raise HTTPException(status_code=400, detail=f"Missing field: {field}")

        # Beräkna lot size
        lot_calc = calculate_lot_size(
            symbol=data["symbol"],
            entry=float(data["entry"]),
            sl=float(data["sl"]),
            balance=ACCOUNT_BALANCE,
            risk_pct=ACCOUNT_RISK_PERCENT,
        )

        # Beräkna TP profit
        tp_profit = calculate_tp_profit(
            symbol=data["symbol"],
            entry=float(data["entry"]),
            tp=float(data["tp"]),
            lot=lot_calc["lot"],
        )

        # Spara i databas
        try:
            note = (
                f"{data.get('trade', '')} | {data.get('session', '')} | RR:{data.get('rr', 0)} | Lot:{lot_calc['lot']} | "
                f"Swept:{data.get('swept', 'MISSING')} | Displacement:{data.get('displacement', 'unknown')} | "
                f"PD:{data.get('pd_zone', 'unknown')} | AsiaWide:{data.get('asia_wide', False)} | "
                f"AfterManip:{data.get('after_manipulation', False)} | TF:{data.get('tf', '')}"
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

        # Bygg Telegram-meddelande
        msg = format_telegram_message(data, lot_calc, tp_profit)

        # Posta till Telegram-gruppen
        try:
            await telegram_bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode="HTML",
            )
            logger.info("Posted to Telegram")
            alert_summary = (
                f"TradingView alert received: {data.get('symbol')} {data.get('side')} {data.get('trade')} "
                f"entry={data.get('entry')} sl={data.get('sl')} tp={data.get('tp')} rr={data.get('rr')} tf={data.get('tf')}"
            )
            await save_message(
                chat_id=TELEGRAM_CHAT_ID,
                user_id=None,
                username="TradingView",
                role="system",
                text=alert_summary,
            )
        except Exception as e:
            logger.error(f"Failed to post to Telegram: {e}")
            raise HTTPException(status_code=500, detail=f"Telegram error: {e}")

        return {
            "status": "ok",
            "lot": lot_calc["lot"],
            "risk_dollars": lot_calc["risk_dollars"],
            "tp_profit": tp_profit,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/test")
async def test_endpoint():
    """Test-endpoint för att verifiera att Telegram funkar."""
    try:
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="✅ <b>Webhook test</b>\nWiseMind webhook receiver fungerar!",
            parse_mode="HTML",
        )
        return {"status": "Test message sent"}
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
