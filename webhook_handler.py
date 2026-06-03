"""
Webhook handler för TradingView-alerts.
Tar emot JSON från Pine Script v9.25+, sparar i DB, postar till Telegram,
och exekverar trades automatiskt på MT5 via File Bridge EA.

Execution flow (File Bridge — no MetaAPI needed):
  Pine alert → webhook → score → write signal file → WiseMindBridge.mq5 → MT5

Supports: Wise London v1.0 + Wise NY v2.0 — both sessions, all assets.
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from typing import Optional
import re
import httpx
from telegram import Bot
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_SECRET,
    ACCOUNT_BALANCE,
    ACCOUNT_RISK_PERCENT,
    METAAPI_TOKEN,
    METAAPI_ACCOUNT_ID,
    MT5_EXECUTION_ENABLED,
    MT5_DRY_RUN,
    MT5_MIN_GRADE,
    BE_ENABLED,
    BE_TRIGGER_R,
    BE_BUFFER_PIPS,
    BE_POLL_SECONDS,
    EXPIRY_ENABLED,
    EXPIRY_HOURS,
    MAX_TRADES_PER_DAY,
    DAY_RESET_TZ,
    MAX_DAILY_LOSS_PCT,
    ERROR_ALERTS,
)
from database import save_trade, save_message
from signal_utils import evaluate_signal
import mt5_executor
import daily_limit
import safety

# WiseMind HQ forwarding — set WISEMIND_HQ_URL in .env if needed
WISEMIND_HQ_URL = os.getenv("WISEMIND_HQ_URL", "")

logger = logging.getLogger(__name__)


# ── FastAPI lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — connect to MetaAPI
    if MT5_EXECUTION_ENABLED:
        logger.info("MetaAPI: initializing MT5 connection...")
        ok = await mt5_executor.init_connection(METAAPI_TOKEN, METAAPI_ACCOUNT_ID)
        if not ok:
            logger.warning("⚠️  MetaAPI init failed — webhook will run WITHOUT MT5 execution")
        elif BE_ENABLED or EXPIRY_ENABLED:
            # Position monitor = breakeven (SL→entry at trigger_r) + time-expiry (auto-close)
            be_trigger = BE_TRIGGER_R if BE_ENABLED else 10_000.0   # huge = effectively off
            exp_hours  = EXPIRY_HOURS if EXPIRY_ENABLED else 0.0     # 0 = off
            mt5_executor.start_position_monitor(be_trigger, BE_BUFFER_PIPS, exp_hours, BE_POLL_SECONDS)
        else:
            logger.info("Position monitor disabled (BE_ENABLED=false, EXPIRY_ENABLED=false)")
    elif MT5_DRY_RUN:
        logger.info("🔬 MT5 DRY RUN mode — trades logged but NOT sent to MetaAPI")
    else:
        logger.info("MT5 execution disabled — set MT5_EXECUTION_ENABLED=true in .env to enable")
    yield
    # Shutdown
    mt5_executor.stop_position_monitor()
    await mt5_executor.close_connection()


# FastAPI app
app = FastAPI(title="WiseMind Webhook Receiver", lifespan=lifespan)

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


def format_telegram_message(data: dict, lot_calc: dict, tp_profit: float, evaluation: dict, exec_result: Optional[dict] = None) -> str:
    """Bygger ett snyggt formatterat Telegram-meddelande från alert data + signal evaluation (v9.22)."""
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
    # v9.22 fields
    tf_type = str(data.get("tf_type", data.get("tf", ""))).upper()
    conflict_resolved = data.get("conflict_resolved", False)
    pine_version = data.get("version", "")

    profile_tag = f" [{profile}]" if profile else ""
    # Normalise "London+ext" display → "London+ext" kept as-is (informative)
    session_tag = f" [{session}]" if session else ""
    trade_tag = f" {trade_type}" if trade_type else ""
    tp_source_tag = f" @{tp_src}" if tp_src else ""
    sl_source_tag = f"{sl_src}" if sl_src else ""
    sl_source_has_pips = "pips" in sl_src.lower() if sl_src else False
    rr_tag = f" ({rr}R)" if rr else ""
    tf_tag = f" [{tf_type}]" if tf_type else ""

    msg = f"<b>{arrow} {symbol}{trade_tag}{session_tag}{profile_tag}{tf_tag}</b>\n"
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
    if data.get("fvg_nearby", False):
        flags.append("✦ FVG CONFIRMED")
    if data.get("consolidation", False):
        flags.append("⚠ CONSOLIDATION")
    # v9.25: Signal grade from 223-chart analysis
    sig_grade = data.get("signal_grade", "")
    if sig_grade:
        grade_emoji = "🟢" if sig_grade == "A+" else ("🟡" if sig_grade == "A" else ("🟠" if sig_grade == "B" else "🔴"))
        flags.append(f"{grade_emoji} GRADE {sig_grade}")
    htf_mode = data.get("htf_mode", "")
    if htf_mode and htf_mode != "Off":
        flags.append(f"HTF: {htf_mode}")
    if conflict_resolved:
        flags.append("✓ CONFLICT RESOLVED")
    if asia_wide:
        flags.append("⚠ ASIA WIDE")
    if flags:
        msg += "\n".join(flags) + "\n"

    rating = evaluation.get("rating", "?")
    score = evaluation.get("score", 0)
    pine_scored = evaluation.get("pine_scored", False)
    # 4-tier emoji (A+/A green, B yellow, C red)
    rating_emoji = {"A+": "🟢", "A": "🟢", "B": "🟡", "C": "🔴"}.get(rating, "🔴")

    # Show Pine's raw 0-100 score when available, else /10
    if pine_scored and data.get("quality_score") is not None:
        score_display = f"{data['quality_score']}/100"
        source_tag = " <i>[Pine]</i>"
    else:
        score_display = f"{score}/10"
        source_tag = ""

    msg += f"\n🧠 <b>Signal Quality:</b> {rating_emoji} <b>{rating}</b> ({score_display}){source_tag}\n"

    reasons = evaluation.get("reasons", [])[:5]
    if reasons:
        msg += "<i>" + " | ".join(reasons) + "</i>\n"

    # ── MT5 execution status ──────────────────────────────────────────────────
    if exec_result is not None:
        msg += "\n"
        if exec_result.get("dry_run"):
            msg += f"🔬 <i>DRY RUN — would execute {lot_calc['lot']} lots (grade {exec_result.get('grade', '?')})</i>\n"
        elif exec_result.get("skipped"):
            msg += f"⏭️ <i>MT5 skipped — grade {exec_result.get('grade','?')} below min {exec_result.get('min_grade','?')}</i>\n"
        elif exec_result.get("daily_limit"):
            msg += f"⛔ <b>Daily limit reached</b> ({exec_result.get('used','?')}/{exec_result.get('max','?')}) — <i>signal logged, NOT traded</i>\n"
        elif exec_result.get("paused"):
            msg += "⏸ <b>Bot PAUSED</b> — <i>signal logged, NOT traded</i>\n"
        elif exec_result.get("loss_blocked"):
            msg += f"🛑 <b>Daily loss limit hit</b> (−{exec_result.get('loss_pct','?')}% ≥ −{exec_result.get('max_loss','?')}%) — <i>trading stopped today</i>\n"
        elif exec_result.get("success") is True:
            entry_px = exec_result.get("entry_price", "")
            order_id = exec_result.get("order_id", "")
            entry_str = f" @ {entry_px}" if entry_px else ""
            order_str = f" | #{order_id}" if order_id else ""
            msg += f"✅ <b>MT5 EXECUTED</b> — {lot_calc['lot']} lots{entry_str}{order_str}\n"
        elif exec_result.get("success") is False:
            err = exec_result.get("error", "unknown error")
            msg += f"❌ <b>MT5 FAILED</b> — <i>{err}</i>\n"

    chart_url = get_chart_url(symbol)
    msg += f"\n📊 <a href=\"{chart_url}\">View Chart on TradingView</a>"
    if pine_version:
        msg += f"\n<i>Pine v{pine_version}</i>"
    msg += "\n💾 <i>Sparat i databas</i>"

    return msg


# ==================== TRADE RESULT FORMATTING ====================

def format_result_telegram_message(data: dict, save_info: dict, monthly: list) -> str:
    """Bygger Telegram-meddelande för trade outcome (WIN/LOSS) från Pine v9.23+."""
    result = data.get("result", "?")
    symbol = data.get("symbol", "?")
    side = data.get("side", "?").upper()
    trade_type = data.get("trade", "")
    session = data.get("session", "")
    entry = data.get("entry", 0)
    sl = data.get("sl", 0)
    tp = data.get("tp", 0)
    exit_price = data.get("exit", 0)
    rr_planned = data.get("rr_planned", 0)
    rr_achieved = data.get("rr_achieved", 0)

    if result == "WIN":
        emoji = "✅"
        result_text = f"TP HIT — +{rr_achieved}R"
        header_emoji = "🟢"
    elif result == "BE":
        emoji = "🔒"
        result_text = "BREAKEVEN — 0R"
        header_emoji = "🟡"
    else:
        emoji = "❌"
        result_text = "SL HIT — -1R"
        header_emoji = "🔴"

    arrow = "▲" if side == "LONG" else "▼"
    session_tag = f" [{session}]" if session else ""
    trade_tag = f" {trade_type}" if trade_type else ""

    msg = f"{header_emoji} <b>TRADE RESULT: {result}</b>\n"
    msg += f"{emoji} {arrow} {symbol}{trade_tag}{session_tag}\n\n"
    msg += f"Entry: {entry}\n"
    msg += f"SL: {sl} | TP: {tp}\n"
    msg += f"Exit: <b>{exit_price}</b>\n"
    msg += f"RR: {rr_planned}R planned → <b>{rr_achieved}R achieved</b>\n"

    # Linked trade info
    if save_info.get("matched_trade_id"):
        msg += f"\n🔗 <i>Linked to trade #{save_info['matched_trade_id']}</i>\n"

    # Monthly stats summary
    if monthly:
        msg += "\n📊 <b>Monthly Stats:</b>\n"
        for m in monthly[-3:]:  # Last 3 months
            wr = m["win_rate"]
            be = m.get("be_count", 0)
            be_rate = m.get("be_rate", 0.0)
            wr_emoji = "🟢" if wr >= 65 else ("🟡" if wr >= 50 else "🔴")
            be_txt = f" / {be}BE" if be > 0 else ""
            be_pct = f" | 🔒{be_rate}%" if be > 0 else ""
            msg += (
                f"  {m['month']} {m['year']}: "
                f"{m['wins']}W / {m['losses']}L{be_txt} "
                f"({wr_emoji} {wr}%{be_pct}) "
                f"| {m['total_r']:+.1f}R\n"
            )

    chart_url = get_chart_url(symbol)
    msg += f"\n📊 <a href=\"{chart_url}\">View Chart</a>"
    version = data.get("version", "")
    if version:
        msg += f"\n<i>Pine v{version}</i>"
    msg += "\n💾 <i>Resultat sparat</i>"

    return msg


# ==================== WEBHOOK ENDPOINT ====================

@app.get("/")
async def root():
    return {"status": "WiseMind Webhook Receiver är igång", "version": "9.23"}


# ==================== STAGE-BY-STAGE SETUP ALERTS ====================
import time as _time

# Dedupe: (symbol, stage, session) -> last post timestamp. Suppresses repeats within the window.
_stage_last: dict = {}
_STAGE_DEDUPE_SECONDS = 90

# Only these stages are broadcast (Michael's choice: sweep, armed, invalidated;
# 'fired' goes through the normal execution/signal path).
_STAGE_BROADCAST = {"sweep", "armed", "invalidated"}


async def handle_stage(data: dict):
    """Format + post a clean factual stage line as a setup forms (no Claude narration)."""
    if data.get("secret") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret")

    stage   = str(data.get("stage", "")).lower().strip()
    symbol  = data.get("symbol", "?")
    session = data.get("session", "")
    detail  = str(data.get("detail", "")).strip()

    if stage not in _STAGE_BROADCAST:
        return {"status": "ignored", "stage": stage}

    # Dedupe identical stage spam within the window
    key = (symbol, stage, session)
    now = _time.time()
    if now - _stage_last.get(key, 0) < _STAGE_DEDUPE_SECONDS:
        return {"status": "deduped", "stage": stage}
    _stage_last[key] = now

    sess_tag = f" [{session}]" if session else ""
    if stage == "sweep":
        msg = f"🌊 <b>{symbol}</b>: {detail or 'liquidity swept'} — setup forming{sess_tag}"
    elif stage == "armed":
        msg = f"🔔 <b>{symbol}</b>: criteria met — trade may fire next bar{sess_tag}"
    else:  # invalidated
        msg = f"❌ <b>{symbol}</b>: setup invalidated — {detail or 'stood down'}{sess_tag}"

    try:
        await telegram_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="HTML")
        logger.info(f"Stage posted: {stage} {symbol}{sess_tag}")
    except Exception as e:
        logger.warning(f"Stage post failed: {e}")
    return {"status": "ok", "stage": stage}


@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        data = await request.json()

        # ── v9.23: Trade Result Webhook ──────────────────────────────────────
        if data.get("event") == "trade_result":
            return await handle_trade_result(data)
        # ── End Trade Result routing ─────────────────────────────────────────

        # ── Stage-by-stage setup alerts (sweep / armed / invalidated) ─────────
        if data.get("event") == "stage":
            return await handle_stage(data)
        # ── End Stage routing ────────────────────────────────────────────────

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

        # ── MT5 Auto-Execution (MetaAPI) ──────────────────────────────────────
        exec_result = None
        grade   = evaluation.get("rating", "C")
        session = data.get("session", "")

        if MT5_DRY_RUN:
            exec_result = {"success": None, "dry_run": True, "lot": lot_calc["lot"], "grade": grade}
            logger.info(f"🔬 DRY RUN: would execute → {data['side']} {lot_calc['lot']} {data['symbol']} [{session}] (grade {grade})")

        elif MT5_EXECUTION_ENABLED:
            # ── Phase 0 Safety: kill switch (pause) ───────────────────────────
            if safety.is_paused():
                exec_result = {"success": None, "paused": True, "grade": grade}
                logger.info(f"⏸ PAUSED — signal logged, NOT traded ({data['symbol']} {grade})")

            elif not mt5_executor.should_execute(grade, MT5_MIN_GRADE):
                exec_result = {"success": None, "skipped": True, "grade": grade, "min_grade": MT5_MIN_GRADE}
                logger.info(f"⏭️  MT5 skipped — grade {grade} < min {MT5_MIN_GRADE}")

            else:
                # Hold the lock across check→execute→record so two near-simultaneous
                # signals can never both slip past the daily cap.
                async with daily_limit.LOCK:
                    used = daily_limit.count_today(DAY_RESET_TZ)
                    # ── Daily loss limit ──────────────────────────────────────
                    loss = {"blocked": False, "loss_pct": 0.0}
                    if MAX_DAILY_LOSS_PCT > 0:
                        equity = await mt5_executor.get_account_equity()
                        if equity is not None:
                            loss = safety.check_daily_loss(equity, MAX_DAILY_LOSS_PCT, DAY_RESET_TZ)

                    if used >= MAX_TRADES_PER_DAY:
                        exec_result = {"success": None, "daily_limit": True,
                                       "used": used, "max": MAX_TRADES_PER_DAY}
                        logger.info(f"⛔ Daily cap reached ({used}/{MAX_TRADES_PER_DAY}) — signal NOT traded")
                    elif loss["blocked"]:
                        exec_result = {"success": None, "loss_blocked": True,
                                       "loss_pct": round(loss["loss_pct"], 2), "max_loss": MAX_DAILY_LOSS_PCT}
                        logger.warning(f"🛑 Daily loss limit (-{loss['loss_pct']:.2f}% ≥ -{MAX_DAILY_LOSS_PCT}%) — signal NOT traded")
                    else:
                        logger.info(f"Executing on MT5: {data['side']} {lot_calc['lot']} {data['symbol']} [{session}] (grade {grade}) — {used+1}/{MAX_TRADES_PER_DAY} today")
                        exec_result = await mt5_executor.execute_trade(
                            symbol  = data["symbol"],
                            side    = data["side"],
                            lot     = lot_calc["lot"],
                            sl      = float(data["sl"]),
                            tp      = float(data["tp"]),
                            comment = f"WiseMind {session} {grade}",
                        )
                        if exec_result and exec_result.get("success"):
                            new_count = daily_limit.record(DAY_RESET_TZ)
                            logger.info(f"Daily count now {new_count}/{MAX_TRADES_PER_DAY}")
                            if exec_result.get("order_id"):
                                def _num(v):
                                    try:
                                        return float(v) if v is not None else None
                                    except (TypeError, ValueError):
                                        return None
                                mt5_executor.register_position_settings(
                                    order_id     = exec_result["order_id"],
                                    be_trigger_r = _num(data.get("be_trigger_r")),
                                    expiry_hours = _num(data.get("expiry_hours")),
                                )

            # ── Error alerting: ping Telegram on a failed order ──────────────
            if ERROR_ALERTS and exec_result and exec_result.get("success") is False:
                try:
                    await telegram_bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=(f"❌ <b>EXECUTION FAILED</b>\n{data.get('symbol')} {data.get('side')} "
                              f"[{session}] {grade}\n<i>{exec_result.get('error','unknown error')}</i>\n"
                              f"⚠️ Check the bot."),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Error-alert send failed: {e}")
        # ── End MT5 Execution ─────────────────────────────────────────────────

        try:
            pine_score_str = (
                f"PineScore:{data.get('quality_score', '')}/{data.get('quality_grade', '')} | "
                if data.get("quality_score") is not None else ""
            )
            note = (
                f"{data.get('trade', '')} | {data.get('session', '')} | RR:{data.get('rr', 0)} | Lot:{lot_calc['lot']} | "
                f"Swept:{data.get('swept', '')} | DispATR:{data.get('displacement_atr', 0)} | "
                f"EngulfPct:{data.get('engulf_body_pct', 0)} | VolSpike:{data.get('vol_spike', 0)} | "
                f"HTF:{data.get('htf_aligned', False)} | FVG:{data.get('fvg_nearby', False)} | "
                f"Consol:{data.get('consolidation', False)} | AfterManip:{data.get('after_manipulation', False)} | "
                f"AsiaWide:{data.get('asia_wide', False)} | TF:{data.get('tf', '')} | TFType:{data.get('tf_type', '')} | "
                f"ConflictResolved:{data.get('conflict_resolved', False)} | Ver:{data.get('version', '')} | "
                f"{pine_score_str}Rating:{evaluation['rating']} | Score:{evaluation['score']}/10"
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

        msg = format_telegram_message(data, lot_calc, tp_profit, evaluation, exec_result)

        # Broadcast only to configured Telegram chat_id
        BROADCAST_TARGETS = [TELEGRAM_CHAT_ID]

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
            pine_q = (
                f" | pine_quality={data.get('quality_score')}/{data.get('quality_grade')}"
                if data.get("quality_score") is not None else ""
            )
            alert_summary = (
                f"TradingView alert received: {data.get('symbol')} {data.get('side')} {data.get('trade')} "
                f"entry={data.get('entry')} sl={data.get('sl')} tp={data.get('tp')} rr={data.get('rr')} "
                f"session={data.get('session')} tf_type={data.get('tf_type', data.get('tf', ''))} "
                f"rating={evaluation['rating']} score={evaluation['score']}/10{pine_q} "
                f"ver={data.get('version', 'legacy')}"
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

        # ── Forward to WiseMind HQ dashboard ─────────────────────────────────
        if WISEMIND_HQ_URL:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{WISEMIND_HQ_URL}/webhook",
                        json=data,
                        timeout=5,
                    )
                logger.info(f"Forwarded signal to WiseMind HQ")
            except Exception as e:
                logger.warning(f"HQ forward failed (non-critical): {e}")
        # ── End HQ forwarding ────────────────────────────────────────────────

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


async def handle_trade_result(data: dict):
    """
    Hanterar trade outcome webhook från Pine v9.23+.
    Sparar resultat i DB, uppdaterar matchande trade, skickar Telegram-notis.

    Expected JSON:
    {
      "secret": "wisemind2026", "event": "trade_result",
      "symbol": "XAUUSD", "side": "LONG", "trade": "T2 LONG (AMD)",
      "session": "London", "result": "WIN",
      "entry": 4350.50, "sl": 4345.00, "tp": 4380.00, "exit": 4380.00,
      "rr_planned": 5.4, "rr_achieved": 5.4, "version": "9.23"
    }
    """
    logger.info(f"Trade result received: {data.get('symbol')} {data.get('side')} → {data.get('result')}")

    # Auth
    if data.get("secret") != WEBHOOK_SECRET:
        logger.warning(f"Trade result secret mismatch! Got: {data.get('secret')}")
        raise HTTPException(status_code=401, detail="Invalid secret")

    # Validate required fields
    required = ["symbol", "side", "result", "entry"]
    for field in required:
        if field not in data:
            logger.error(f"Trade result missing field: {field}")
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    result = data.get("result", "").upper()
    if result not in ("WIN", "LOSS", "BE"):
        raise HTTPException(status_code=400, detail=f"Invalid result: {result}")

    # Save to database
    try:
        save_info = await save_trade_result(
            symbol=data["symbol"],
            direction=data["side"],
            result=result,
            entry=float(data.get("entry", 0)),
            sl=float(data.get("sl", 0)),
            tp=float(data.get("tp", 0)),
            exit_price=float(data.get("exit", 0)),
            rr_planned=float(data.get("rr_planned", 0)),
            rr_achieved=float(data.get("rr_achieved", 0)),
            trade_type=data.get("trade", ""),
            session=data.get("session", ""),
            version=data.get("version", ""),
        )
        logger.info(f"Trade result saved: id={save_info['id']}, matched_trade={save_info['matched_trade_id']}")
    except Exception as e:
        logger.error(f"Failed to save trade result: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # Get monthly stats for context
    try:
        monthly = await get_monthly_stats(months=6)
    except Exception as e:
        logger.error(f"Failed to get monthly stats: {e}")
        monthly = []

    # Format and send Telegram message
    msg = format_result_telegram_message(data, save_info, monthly)

    try:
        await telegram_bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info(f"Trade result posted to Telegram")
    except Exception as e:
        logger.error(f"Failed to post trade result to Telegram: {e}")

    # Save to message memory for Claude context
    try:
        rr_str = f"{data.get('rr_achieved', 0)}R" if result == "WIN" else "-1R"
        summary = (
            f"Trade result: {data.get('symbol')} {data.get('side')} {data.get('trade', '')} "
            f"→ {result} ({rr_str}) | Session: {data.get('session', '')} | "
            f"Entry: {data.get('entry')} Exit: {data.get('exit')} | "
            f"ver={data.get('version', '')}"
        )
        await save_message(
            chat_id=TELEGRAM_CHAT_ID,
            user_id=None,
            username="TradingView",
            role="system",
            text=summary,
        )
    except Exception as e:
        logger.error(f"Failed to save result summary: {e}")

    # ── Forward trade result to WiseMind HQ dashboard ────────────────────
    if WISEMIND_HQ_URL:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{WISEMIND_HQ_URL}/webhook",
                    json=data,
                    timeout=5,
                )
            logger.info(f"Forwarded trade result to WiseMind HQ")
        except Exception as e:
            logger.warning(f"HQ result forward failed (non-critical): {e}")
    # ── End HQ forwarding ────────────────────────────────────────────────

    return {
        "status": "ok",
        "event": "trade_result",
        "result": result,
        "result_id": save_info["id"],
        "matched_trade_id": save_info.get("matched_trade_id"),
    }


@app.post("/test")
async def test_endpoint():
    """Test-endpoint för att verifiera Telegram broadcast i konfigurerade grupper."""
    BROADCAST_TARGETS = [TELEGRAM_CHAT_ID]

    results = []
    for target_chat_id in BROADCAST_TARGETS:
        try:
            await telegram_bot.send_message(
                chat_id=target_chat_id,
                text=f"✅ <b>Webhook test</b>\nWiseMind webhook receiver fungerar (v9.22)!\nThis chat_id: <code>{target_chat_id}</code>",
                parse_mode="HTML",
            )
            results.append({"chat_id": target_chat_id, "status": "ok"})
        except Exception as e:
            results.append({"chat_id": target_chat_id, "status": f"error: {e}"})
            logger.error(f"Test failed for chat_id={target_chat_id}: {e}")
    return {"status": "Test broadcast complete", "results": results}
