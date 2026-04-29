"""
Webhook handler för TradingView-alerts.
Tar emot JSON från Pine Script v9.15+, sparar i DB, postar till Telegram.
"""

import logging
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional
from telegram import Bot
from anthropic import Anthropic
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_SECRET,
    ACCOUNT_BALANCE,
    ACCOUNT_RISK_PERCENT,
)
from database import save_trade

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


# ==================== MESSAGE FORMATTING ====================
def format_telegram_message(data: dict, lot_calc: dict, tp_profit: float) -> str:
    """Bygger ett snyggt formatterat Telegram-meddelande från alert data."""
    side = data.get("side", "?").upper()
    arrow = "▲" if side == "LONG" else "▼"
    symbol = data.get("symbol", "?")
    trade_type = data.get("trade", "?")
    session = data.get("session", "?")
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

    msg = f"<b>{arrow} {symbol} {trade_type} [{session}]{profile_tag}</b>\n"
    msg += f"Entry: <b>{entry}</b>\n"
    msg += f"SL: <b>{sl}</b> ({sl_src}, {lot_calc['sl_pips']} pips)\n"
    msg += f"TP: <b>{tp}</b> @{tp_src} ({rr}R)\n"
    msg += f"\n💰 <b>Lot: {lot_calc['lot']}</b> | Risk: ${lot_calc['risk_dollars']} | TP profit: ${tp_profit}\n"

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
            note = f"{data.get('trade', '')} | {data.get('session', '')} | RR: {data.get('rr', 0)} | Lot: {lot_calc['lot']}"
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
