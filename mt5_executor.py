"""
MT5 execution layer via MetaAPI cloud.
Handles connection management and trade execution for WiseMind v9.22.

Flow:
  webhook_handler.py → execute_trade() → MetaAPI cloud → MT5 (Wine) → broker
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────────────────
_api        = None
_connection = None
_connected  = False

# Grade priority for min-grade filter
GRADE_ORDER = {"A+": 3, "B": 2, "C": 1}


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

    options = {"comment": comment, "clientId": "wisemind"}

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
