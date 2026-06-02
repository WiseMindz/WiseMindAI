"""
Daily trade-cap — hard global limit on how many trades the bot executes per day.

Strict rule (Michael): once the day's quota of EXECUTED trades is reached, the bot
ignores ALL further signals that day — every asset, every session, every indicator.
Only a *real filled* trade counts (grade-skipped / failed orders do NOT burn a slot).

The count is persisted to a small JSON file so a bot restart cannot sneak in an extra
trade. "Day" = calendar date in DAY_RESET_TZ (default Europe/Stockholm / CEST).
"""

import os
import json
import asyncio
import logging
import datetime

logger = logging.getLogger(__name__)

# Serializes the check→execute→record sequence so two near-simultaneous signals
# can never both slip through the cap.
LOCK = asyncio.Lock()

_STATE_PATH = os.getenv(
    "DAILY_STATE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_trades.json"),
)


def _today_str(tz_name: str) -> str:
    """Current calendar date (YYYY-MM-DD) in the configured timezone, UTC fallback."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        with open(_STATE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(state: dict) -> None:
    try:
        with open(_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"daily_limit: could not write state: {e}")


def count_today(tz_name: str) -> int:
    """How many trades have been executed so far today (0 if a new day)."""
    state = _load()
    return int(state.get("count", 0)) if state.get("date") == _today_str(tz_name) else 0


def record(tz_name: str) -> int:
    """Register one executed trade for today. Returns the new count."""
    today = _today_str(tz_name)
    state = _load()
    count = (int(state.get("count", 0)) + 1) if state.get("date") == today else 1
    _save({"date": today, "count": count})
    return count


def remaining(max_per_day: int, tz_name: str) -> int:
    """Trades still allowed today."""
    return max(0, max_per_day - count_today(tz_name))
