"""
Phase 0 safety state — kill switch (pause) + daily loss limit baseline.

Persists to a JSON file next to DAILY_STATE_PATH so state survives bot restarts
(on a Railway volume it survives redeploys too). "Day" = calendar date in the
configured timezone (matches daily_limit).

State file shape:
  {
    "paused": false,
    "loss_day": "2026-06-02",
    "day_start_equity": 100000.0,
    "loss_blocked": false        # set true once the daily loss limit is breached today
  }
"""

import os
import json
import logging
import datetime

logger = logging.getLogger(__name__)

# Store bot_state.json in the same directory as the daily-cap file (the volume)
_DAILY_PATH = os.getenv(
    "DAILY_STATE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_trades.json"),
)
_STATE_PATH = os.path.join(os.path.dirname(_DAILY_PATH) or ".", "bot_state.json")


def _today(tz_name: str) -> str:
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
        os.makedirs(os.path.dirname(_STATE_PATH) or ".", exist_ok=True)
        with open(_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"safety: could not write state: {e}")


# ── Kill switch ───────────────────────────────────────────────────────────────

def is_paused() -> bool:
    return bool(_load().get("paused", False))


def set_paused(paused: bool) -> None:
    state = _load()
    state["paused"] = bool(paused)
    _save(state)
    logger.info(f"⏸ Bot {'PAUSED' if paused else 'RESUMED'} via kill switch")


# ── Daily loss limit ──────────────────────────────────────────────────────────

def check_daily_loss(current_equity: float, max_loss_pct: float, tz_name: str) -> dict:
    """
    Compare current equity to today's day-start equity. Records the day-start
    baseline lazily on first call of a new day. Returns:
      {"blocked": bool, "loss_pct": float, "start_equity": float}
    `blocked` is True once the loss limit has been breached today (sticky for the day).
    max_loss_pct = 0 disables the check.
    """
    today = _today(tz_name)
    state = _load()

    # New day → reset baseline + unblock
    if state.get("loss_day") != today:
        state["loss_day"] = today
        state["day_start_equity"] = current_equity
        state["loss_blocked"] = False
        _save(state)

    # Lazy baseline if missing
    if not state.get("day_start_equity"):
        state["day_start_equity"] = current_equity
        _save(state)

    start = float(state.get("day_start_equity") or current_equity)
    if max_loss_pct <= 0 or start <= 0:
        return {"blocked": False, "loss_pct": 0.0, "start_equity": start}

    loss_pct = max(0.0, (start - current_equity) / start * 100.0)

    if state.get("loss_blocked"):
        return {"blocked": True, "loss_pct": loss_pct, "start_equity": start}

    if loss_pct >= max_loss_pct:
        state["loss_blocked"] = True
        _save(state)
        logger.warning(f"🛑 Daily loss limit hit: -{loss_pct:.2f}% (start {start}) — trading blocked today")
        return {"blocked": True, "loss_pct": loss_pct, "start_equity": start}

    return {"blocked": False, "loss_pct": loss_pct, "start_equity": start}


def check_total_drawdown(current_equity: float, start_balance: float, max_dd_pct: float) -> dict:
    """
    Max TOTAL drawdown guard (vs the challenge start balance). When equity drops
    >= max_dd_pct below start_balance, set a STICKY block + auto-pause the bot.
    Returns {"blocked": bool, "dd_pct": float}. max_dd_pct = 0 disables.
    """
    if max_dd_pct <= 0 or not start_balance or start_balance <= 0:
        return {"blocked": False, "dd_pct": 0.0}

    dd_pct = max(0.0, (start_balance - current_equity) / start_balance * 100.0)
    state = _load()

    if state.get("dd_blocked"):
        return {"blocked": True, "dd_pct": dd_pct}

    if dd_pct >= max_dd_pct:
        state["dd_blocked"] = True
        state["paused"] = True          # auto-pause so NO new trades fire
        _save(state)
        logger.warning(f"🛑 MAX DRAWDOWN hit: -{dd_pct:.2f}% (start {start_balance}) — bot AUTO-PAUSED")
        return {"blocked": True, "dd_pct": dd_pct}

    return {"blocked": False, "dd_pct": dd_pct}


def dd_status() -> dict:
    s = _load()
    return {"blocked": bool(s.get("dd_blocked", False))}


def loss_status(tz_name: str) -> dict:
    """Read-only snapshot for /status (does not record a baseline)."""
    state = _load()
    return {
        "blocked": bool(state.get("loss_blocked", False)) and state.get("loss_day") == _today(tz_name),
        "start_equity": state.get("day_start_equity"),
        "loss_day": state.get("loss_day"),
    }
