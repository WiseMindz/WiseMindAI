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

# ==================== METAAPI (MT5 AUTO-EXECUTION) ====================
METAAPI_TOKEN      = os.getenv("METAAPI_TOKEN", "")
METAAPI_ACCOUNT_ID = os.getenv("METAAPI_ACCOUNT_ID", "")

# Set MT5_EXECUTION_ENABLED=true in .env to go live
MT5_EXECUTION_ENABLED = os.getenv("MT5_EXECUTION_ENABLED", "false").lower() == "true"

# Dry-run: calculates + logs everything but does NOT send order to MT5
MT5_DRY_RUN = os.getenv("MT5_DRY_RUN", "false").lower() == "true"

# Minimum signal grade to execute: "A+" = only A+, "B" = A+ and B, "C" = all
MT5_MIN_GRADE = os.getenv("MT5_MIN_GRADE", "B")

