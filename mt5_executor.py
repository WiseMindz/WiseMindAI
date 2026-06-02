"""
MT5 execution layer via MetaAPI cloud.
Handles connection management and trade execution for WiseMind v9.22.

Flow:
  webhook_handler.py → execute_trade() → MetaAPI cloud → MT5 (Wine) → broker
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────
_api        = None
_connection = None
_connected  = False

# Grade priority for min-grade filter — 4-tier, synced with the indicator (A+ > A > B > C)
GRADE_ORDER = {"A+": 4, "A": 3, "B": 2, "C": 1}


# ── Connection lifecycle ──────────────────────────────────────────────────────

async def init_connection(token: str, account_id: str) -> bool:
    """
    Initialize MetaAPI connection at app startup.
    Returns True if connected and synchronized, False on failure.
    """
    global _api, _connection, _connected

    if not token or not account_id:
        logger.warning("MetaAPI: token or account_id missing — execution disabled")
        return False

    try:
        from metaapi_cloud_sdk import MetaApi  # imported here so missing lib doesn't crash startup

        _api    = MetaApi(token)
        account = await _api.metatrader_account_api.get_account(account_id)

        if account.state not in ["DEPLOYING", "DEPLOYED"]:
            logger.info("MetaAPI: deploying account...")
            await account.deploy()

        logger.info("MetaAPI: waiting for broker connection...")
        await account.wait_connected()

        _connection = account.get_rpc_connection()
        await _connection.connect()
        await _connection.wait_synchronized()

        _connected = True
        logger.info("✅ MetaAPI: connected and synchronized")
        return True

    except ImportError:
        logger.error("MetaAPI: metaapi-cloud-sdk not installed — run: pip install metaapi-cloud-sdk")
        _connected = False
        return False
    except Exception as e:
        logger.error(f"❌ MetaAPI init failed: {type(e).__name__}: {e}")
        _connected = False
        return False


async def close_connection() -> None:
    """Close MetaAPI connection gracefully at app shutdown."""
    global _connection, _connected
    if _connection:
        try:
            await _connection.close()
            logger.info("MetaAPI: connection closed")
        except Exception:
            pass
    _connected = False


def is_connected() -> bool:
    return _connected


# ── Grade filter ──────────────────────────────────────────────────────────────

def should_execute(rating: str, min_grade: str) -> bool:
    """
    Returns True if signal grade meets the minimum execution threshold.
    A+ > B > C.  Default min_grade = "B" (executes A+ and B, skips C).
    """
    return GRADE_ORDER.get(rating, 0) >= GRADE_ORDER.get(min_grade, 2)


# ── Trade execution ───────────────────────────────────────────────────────────

async def execute_trade(
    symbol:  str,
    side:    str,
    lot:     float,
    sl:      float,
    tp:      float,
    comment: str = "WiseMind v9.22",
) -> dict:
    """
    Place a market order on MT5 via MetaAPI.

    Returns:
        {success: True,  order_id: "...", entry_price: 1.16925}
        {success: False, error: "..."}
    """
    global _connection, _connected

    if not _connected or _connection is None:
        return {"success": False, "error": "MetaAPI not connected"}

    if lot <= 0:
        return {"success": False, "error": f"Invalid lot: {lot}"}

    # MetaAPI rejects '+' and most symbols in comment — keep only safe chars, max 25
    safe_comment = re.sub(r"[^A-Za-z0-9 _]", "", comment)[:25] or "WiseMind"
    options = {"comment": safe_comment}

    try:
        if side.upper() == "LONG":
            result = await _connection.create_market_buy_order(symbol, lot, sl, tp, options)
        else:
            result = await _connection.create_market_sell_order(symbol, lot, sl, tp, options)

        order_id    = str(result.get("orderId") or result.get("positionId") or "")
        entry_price = result.get("openPrice", 0)

        logger.info(f"✅ MT5 executed: {side} {lot} {symbol} @ {entry_price} | #{order_id}")

        return {"success": True, "order_id": order_id, "entry_price": entry_price}

    except Exception as e:
        err = str(e)[:150]
        logger.error(f"❌ MT5 execution error: {type(e).__name__}: {err}")
        return {"success": False, "error": err}


# ── Position monitor: breakeven + time-expiry ─────────────────────────────────
# Replicates the Pine trade-management settings on the REAL broker:
#   • "Auto Move SL to Breakeven" (beThresholdR) → move SL to entry at trigger_r.
#   • "Auto-close after N hours"   (tradeExpiryHours) → force-close stale positions.
# Per-position settings can be sent by Pine in the webhook (be_trigger_r / expiry_hours);
# if not sent, the global .env defaults are used (so nothing breaks today).

import asyncio
import datetime

# Minimal pip-size map for the optional BE buffer (price distance per pip)
_PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCHF": 0.0001, "USDJPY": 0.01,   "USDCAD": 0.0001, "CHFJPY": 0.01,
    "XAUUSD": 0.10,   "XAGUSD": 0.001,
}

_be_done: set = set()        # positions already moved to BE this run
_pos_settings: dict = {}     # order_id -> {"be_trigger_r","be_buffer_pips","expiry_hours"} (from webhook)
_monitor_task = None


def _pip_size(symbol: str) -> float:
    clean = symbol.upper().replace(".", "").replace("_", "")[:6]
    return _PIP_SIZE.get(clean, 0.0001)


def register_position_settings(order_id: str, be_trigger_r=None, be_buffer_pips=None, expiry_hours=None):
    """Record per-position management settings (from the Pine webhook) for the monitor to use.
    Any value left None falls back to the global .env default at check time."""
    if not order_id:
        return
    _pos_settings[str(order_id)] = {
        "be_trigger_r":   be_trigger_r,
        "be_buffer_pips": be_buffer_pips,
        "expiry_hours":   expiry_hours,
    }


def _setting(pid: str, key: str, default):
    s = _pos_settings.get(str(pid))
    if s and s.get(key) is not None:
        return s[key]
    return default


async def _check_breakeven_once(default_trigger_r: float, default_buffer_pips: float) -> None:
    """One pass: move SL→breakeven for any position that reached its trigger_r."""
    global _connection, _be_done
    if not _connected or _connection is None:
        return

    positions = await _connection.get_positions()
    live_ids = set()

    for pos in positions:
        pid = str(pos.get("id"))
        live_ids.add(pid)
        if pid in _be_done:
            continue

        entry  = pos.get("openPrice")
        sl     = pos.get("stopLoss")
        tp     = pos.get("takeProfit")
        ptype  = pos.get("type", "")        # POSITION_TYPE_BUY / POSITION_TYPE_SELL
        symbol = pos.get("symbol", "")

        if not entry or not sl:
            continue
        risk = abs(entry - sl)
        if risk < 1e-9:                      # SL already ≈ entry → already BE
            _be_done.add(pid)
            continue

        try:
            price = await _connection.get_symbol_price(symbol)
        except Exception:
            continue

        is_buy = "BUY" in ptype.upper()
        cur_price = price.get("bid") if is_buy else price.get("ask")
        if cur_price is None:
            continue
        profit_dist = (cur_price - entry) if is_buy else (entry - cur_price)

        trigger_r   = _setting(pid, "be_trigger_r",   default_trigger_r)
        buffer_pips = _setting(pid, "be_buffer_pips", default_buffer_pips)

        if (profit_dist / risk) < trigger_r:
            continue

        buf = buffer_pips * _pip_size(symbol)
        new_sl = round(entry + buf, 5) if is_buy else round(entry - buf, 5)
        try:
            await _connection.modify_position(pid, stop_loss=new_sl, take_profit=tp)
            _be_done.add(pid)
            logger.info(
                f"🔒 BE moved: #{pid} {symbol} {'BUY' if is_buy else 'SELL'} "
                f"@ {profit_dist/risk:.2f}R → SL {new_sl} (was {sl})"
            )
        except Exception as e:
            logger.error(f"❌ BE modify failed #{pid}: {type(e).__name__}: {str(e)[:120]}")

    # Prune state for closed positions
    _be_done = _be_done & live_ids
    for gone in [k for k in _pos_settings if k not in live_ids]:
        _pos_settings.pop(gone, None)


async def _check_expiry_once(default_expiry_hours: float) -> None:
    """One pass: force-close any position older than its expiry_hours (mirrors Pine tradeExpiryHours)."""
    global _connection
    if not _connected or _connection is None:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    positions = await _connection.get_positions()

    for pos in positions:
        pid = str(pos.get("id"))
        expiry_hours = _setting(pid, "expiry_hours", default_expiry_hours)
        if not expiry_hours or expiry_hours <= 0:     # 0 / None = expiry disabled
            continue

        opened = pos.get("time")
        if isinstance(opened, str):
            try:
                opened = datetime.datetime.fromisoformat(opened.replace("Z", "+00:00"))
            except Exception:
                continue
        if not isinstance(opened, datetime.datetime):
            continue
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=datetime.timezone.utc)

        age_hours = (now - opened).total_seconds() / 3600.0
        if age_hours < expiry_hours:
            continue

        try:
            await _connection.close_position(pid)
            logger.info(
                f"⏱ EXPIRY close: #{pid} {pos.get('symbol','')} open {age_hours:.1f}h "
                f"≥ {expiry_hours}h → force-closed at market"
            )
        except Exception as e:
            logger.error(f"❌ Expiry close failed #{pid}: {type(e).__name__}: {str(e)[:120]}")


async def run_position_monitor(be_trigger_r: float, be_buffer_pips: float,
                               expiry_hours: float, poll_seconds: int) -> None:
    """Background loop: every poll_seconds, run breakeven + expiry management on open positions."""
    logger.info(
        f"🔒 Position monitor started — BE trigger {be_trigger_r}R / buffer {be_buffer_pips} pips, "
        f"expiry {expiry_hours}h (0=off), poll {poll_seconds}s"
    )
    while True:
        try:
            await _check_breakeven_once(be_trigger_r, be_buffer_pips)
            await _check_expiry_once(expiry_hours)
        except asyncio.CancelledError:
            logger.info("🔒 Position monitor stopped")
            raise
        except Exception as e:
            logger.error(f"Position monitor loop error: {type(e).__name__}: {str(e)[:120]}")
        await asyncio.sleep(poll_seconds)


def start_position_monitor(be_trigger_r: float, be_buffer_pips: float,
                           expiry_hours: float, poll_seconds: int):
    """Create and track the position-monitor background task. Returns the task."""
    global _monitor_task
    _monitor_task = asyncio.create_task(
        run_position_monitor(be_trigger_r, be_buffer_pips, expiry_hours, poll_seconds)
    )
    return _monitor_task


def stop_position_monitor():
    """Cancel the position-monitor task if running."""
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
    _monitor_task = None
