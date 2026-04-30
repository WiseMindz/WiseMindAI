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
WEBHOOK_PORT = get_int_env("PORT", get_int_env("WEBHOOK_PORT", 8000))

# ==================== ACCOUNT (LOT SIZE BERÄKNING) ====================
# Konto-info för auto lot size
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 50000))
ACCOUNT_RISK_PERCENT = float(os.getenv("ACCOUNT_RISK_PERCENT", 1.0))
ACCOUNT_CURRENCY = os.getenv("ACCOUNT_CURRENCY", "USD")

