"""
Pytest bootstrap for the WiseMind bot test suite.

Runs BEFORE any project module is imported. We force hermetic, SAFE dummy
environment variables here so that:
  • importing `config` never raises on a missing key (CI has no .env),
  • the test process never loads the REAL Telegram token / Claude key (config's
    load_dotenv() uses override=False, so these pre-set values win over .env), and
  • the daily-cap / safety state files are written to a throwaway temp dir, never
    the real daily_trades.json / bot_state.json.
"""

import os
import tempfile

# Safe dummy secrets (real .env is intentionally ignored during tests).
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST_TOKEN"
os.environ["TELEGRAM_CHAT_ID"] = "-1000000000001"
os.environ["CLAUDE_API_KEY"] = "sk-ant-test-key"
os.environ["WEBHOOK_SECRET"] = "wisemind2026"

# Never touch the real state files — point them at a throwaway dir.
_TMP_STATE_DIR = tempfile.mkdtemp(prefix="wm_test_state_")
os.environ["DAILY_STATE_PATH"] = os.path.join(_TMP_STATE_DIR, "daily_trades.json")
