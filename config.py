import os
from dotenv import load_dotenv

load_dotenv()

# ==================== TELEGRAM ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))

# ==================== CLAUDE ====================
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"
CLAUDE_MODEL_SMART = "claude-sonnet-4-6"
CLAUDE_MODEL = CLAUDE_MODEL_SMART

# ==================== WEBHOOK ====================
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "wisemind2026")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8000))

# ==================== ACCOUNT (LOT SIZE BERÄKNING) ====================
# Konto-info för auto lot size
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 50000))
ACCOUNT_RISK_PERCENT = float(os.getenv("ACCOUNT_RISK_PERCENT", 1.0))
ACCOUNT_CURRENCY = os.getenv("ACCOUNT_CURRENCY", "USD")

