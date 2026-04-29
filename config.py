import os
from dotenv import load_dotenv

load_dotenv()

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "wisemind2026")

CLAUDE_MODEL_FAST = "claude-haiku-4-5-20251001"
CLAUDE_MODEL_SMART = "claude-sonnet-4-6"
CLAUDE_MODEL = CLAUDE_MODEL_SMART

PORT = int(os.getenv("PORT", 8000))
