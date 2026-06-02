"""
MT5 File Bridge — WiseMind auto-execution without MetaAPI.

Flow:
  webhook_handler.py → write_signal() → wisemind_TIMESTAMP.txt
                                              ↓
                          WiseMindBridge.mq5 reads it (every 500ms)
                                              ↓
                                    MT5 executes the trade

Supports: London + NY sessions, T1 + T2, EURUSD / XAUUSD / CHFJPY
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

GRADE_ORDER = {"A+": 3, "B": 2, "C": 1}


def should_execute(rating: str, min_grade: str) -> bool:
    """Return True if signal grade meets the minimum threshold. A+ > B > C."""
    return GRADE_ORDER.get(rating, 0) >= GRADE_ORDER.get(min_grade, 2)


def is_configured(signals_path: str) -> bool:
    """Return True if the bridge folder exists and is reachable."""
    return bool(signals_path) and os.path.isdir(signals_path)


async def execute_trade(
    symbol:       str,
    side:         str,
    lot:          float,
    sl:           float,
    tp:           float,
    session:      str  = "",
    grade:        str  = "",
    comment:      str  = "WiseMind",
    signals_path: str  = "",
    dry_run:      bool = False,
) -> dict:
    """
    Write a signal file that WiseMindBridge.mq5 will pick up and execute.

    Returns:
        {success: True,  filename: "wisemind_1717200000000.txt"}
        {success: False, error: "..."}
        {success: None,  dry_run: True, filename: "..."}   ← dry run
    """
    if lot <= 0:
        return {"success": False, "error": f"Invalid lot size: {lot}"}

    if not signals_path:
        return {"success": False, "error": "BRIDGE_SIGNALS_PATH not set in .env"}

    # Auto-create folder if missing
    if not os.path.isdir(signals_path):
        try:
            os.makedirs(signals_path, exist_ok=True)
            logger.info(f"Created signals folder: {signals_path}")
        except Exception as e:
            return {"success": False, "error": f"Cannot create signals folder: {e}"}

    timestamp = int(datetime.now().timestamp() * 1000)
    filename  = f"wisemind_{timestamp}.txt"
    filepath  = os.path.join(signals_path, filename)

    # Key=value format — simple for MQL5 to parse
    content = (
        f"SYMBOL={symbol.upper()}\n"
        f"SIDE={side.upper()}\n"
        f"LOT={lot}\n"
        f"SL={sl}\n"
        f"TP={tp}\n"
        f"SESSION={session}\n"
        f"GRADE={grade}\n"
        f"COMMENT={comment}\n"
        f"TIMESTAMP={timestamp}\n"
    )

    if dry_run:
        logger.info(f"🔬 DRY RUN — would write: {filename}\n{content}")
        return {"success": None, "dry_run": True, "filename": filename}

    try:
        with open(filepath, "w") as f:
            f.write(content)
        logger.info(f"✅ Signal written → {filepath}")
        return {"success": True, "filename": filename, "path": filepath}

    except Exception as e:
        err = str(e)[:150]
        logger.error(f"❌ Bridge write failed: {err}")
        return {"success": False, "error": err}
