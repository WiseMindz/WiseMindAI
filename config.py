import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def get_int_env(key: str, default: Optional[int] = None, required: bool = False) -> Optional[int]:
    value = os.getenv(key)
    if value is None or value == "":
        if required and default is None:
            raise ValueError(f"Missing required environment variable: {key}")
        return default
    return int(value)


# ==================== TELEGRAM ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing required environment variable: TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_int_env("TELEGRAM_CHAT_ID", required=True)

# ==================== CLAUDE ====================
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
if not CLAUDE_API_KEY:
    raise ValueError("Missing required environment variable: CLAUDE_API_KEY")

CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"
CLAUDE_MODEL_SMART = "claude-sonnet-4-6"
CLAUDE_MODEL = CLAUDE_MODEL_SMART

# ==================== WEBHOOK ====================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "wisemind2026")
# Railway sätter automatiskt PORT — använd den om den finns, annars fallback till 8000
WEBHOOK_PORT = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8000")))

# ==================== ACCOUNT (LOT SIZE BERÄKNING) ====================
# Konto-info för auto lot size
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 50000))
ACCOUNT_RISK_PERCENT = float(os.getenv("ACCOUNT_RISK_PERCENT", 1.0))
ACCOUNT_CURRENCY = os.getenv("ACCOUNT_CURRENCY", "USD")

# ==================== MT5 FILE BRIDGE (AUTO-EXECUTION) ====================
# Path where Python writes signal files and the WiseMindBridge EA reads them.
# Set this to your MT5 data folder → MQL5/Files/wisemind/
# Find it: open MT5 → File → Open Data Folder → MQL5/Files → create "wisemind" subfolder
BRIDGE_SIGNALS_PATH = os.getenv("BRIDGE_SIGNALS_PATH", "")

# Set MT5_EXECUTION_ENABLED=true in .env to go live
MT5_EXECUTION_ENABLED = os.getenv("MT5_EXECUTION_ENABLED", "false").lower() == "true"

# Dry-run: logs everything but does NOT write signal files to MT5
MT5_DRY_RUN = os.getenv("MT5_DRY_RUN", "true").lower() == "true"

# Minimum signal grade to execute: "A+" = only A+, "B" = A+ and B, "C" = all
MT5_MIN_GRADE = os.getenv("MT5_MIN_GRADE", "B")

# Only execute 5m structure entries — skip 1m precision fires (tiny SL → oversized lot).
EXECUTE_ONLY_5M = os.getenv("EXECUTE_ONLY_5M", "true").lower() == "true"
# Hard cap on lot size — skip any order bigger than this (prevents "not enough money").
MAX_LOT_SIZE    = float(os.getenv("MAX_LOT_SIZE", "5.0"))   # 0 = no cap
# Hard cap on $ RISKED per trade — overrides ACCOUNT_BALANCE × ACCOUNT_RISK_PERCENT if that would
# risk more. Belt-and-suspenders so a wrong balance/risk% can NEVER over-risk the funded account.
MAX_RISK_DOLLARS = float(os.getenv("MAX_RISK_DOLLARS", "0"))   # 0 = off; set 500 on a $50k account

# ── LEARNING BRAIN: broker-truth reconciliation (read-only deal history → complete record) ──
RECONCILE_ENABLED      = os.getenv("RECONCILE_ENABLED", "false").lower() == "true"  # OFF until enabled
RECONCILE_POLL_SECONDS = int(os.getenv("RECONCILE_POLL_SECONDS", "900"))            # 15 min
RECONCILE_LOOKBACK_HRS = float(os.getenv("RECONCILE_LOOKBACK_HRS", "48"))           # window per pass

# ── Breakeven monitor (replicates Pine "Auto Move SL to Breakeven") ───────────
# When an open position reaches BE_TRIGGER_R profit, its SL is moved to entry.
BE_ENABLED      = os.getenv("BE_ENABLED", "true").lower() == "true"
BE_TRIGGER_R    = float(os.getenv("BE_TRIGGER_R", "1.5"))   # matches Pine beThresholdR default
BE_BUFFER_PIPS  = float(os.getenv("BE_BUFFER_PIPS", "0"))   # 0 = pure breakeven (entry)
BE_POLL_SECONDS = int(os.getenv("BE_POLL_SECONDS", "15"))   # how often to check positions

# ── Time-expiry (replicates Pine "Auto-close after N hours" / tradeExpiryHours) ─
EXPIRY_ENABLED  = os.getenv("EXPIRY_ENABLED", "true").lower() == "true"
EXPIRY_HOURS    = float(os.getenv("EXPIRY_HOURS", "24"))    # 0 = off; matches Pine default 24h

# ── Daily trade cap (hard global limit — once reached, no more trades that day) ─
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "1"))      # strict 1/day by default
DAY_RESET_TZ       = os.getenv("DAY_RESET_TZ", "Europe/Stockholm")  # CEST day boundary

# ── Phase 0 Safety: kill switch, daily loss limit, error alerts ────────────────
ADMIN_USER_ID      = get_int_env("ADMIN_USER_ID", default=0)        # Telegram user allowed to /pause /resume (0 = anyone)
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0"))    # auto-stop at -X% equity for the day (0 = off)
# Max TOTAL drawdown from the challenge start balance (ACCOUNT_BALANCE). Blocks new
# trades + auto-pauses when equity drops this % below start. Keep UNDER the prop firm's
# max-DD rule (e.g. 8 when FundingTraders allows ~10%). 0 = off.
MAX_TOTAL_DD_PCT   = float(os.getenv("MAX_TOTAL_DD_PCT", "0"))
ERROR_ALERTS       = os.getenv("ERROR_ALERTS", "true").lower() == "true"  # Telegram ping on failed order / disconnect

# ── Phase 1 Brain: daily briefings ─────────────────────────────────────────────
BRIEFINGS_ENABLED  = os.getenv("BRIEFINGS_ENABLED", "true").lower() == "true"
BRIEF_MORNING      = os.getenv("BRIEF_MORNING", "08:30")   # CEST pre-London
BRIEF_EVENING      = os.getenv("BRIEF_EVENING", "17:30")   # CEST post-NY

# Legacy MetaAPI vars (kept so config doesn't break if still in .env)
METAAPI_TOKEN      = os.getenv("METAAPI_TOKEN", "")
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")

