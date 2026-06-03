"""
Safety-gate tests: grade filter, daily trade cap, kill switch, daily loss limit.

These are the bot's circuit breakers. Each one must block at EXACTLY its threshold
and must fail safe. A gate that "fails open" = an unwanted real trade.
"""

import pytest

import mt5_executor
import daily_limit
import safety


# ── Grade filter (mt5_executor.should_execute) — 4-tier A+>A>B>C ──────────────────

def test_min_grade_b_takes_aplus_a_b_skips_c():
    assert mt5_executor.should_execute("A+", "B") is True
    assert mt5_executor.should_execute("A", "B") is True
    assert mt5_executor.should_execute("B", "B") is True
    assert mt5_executor.should_execute("C", "B") is False


def test_min_grade_a_takes_only_aplus_and_a():
    assert mt5_executor.should_execute("A+", "A") is True
    assert mt5_executor.should_execute("A", "A") is True
    assert mt5_executor.should_execute("B", "A") is False


def test_min_grade_aplus_only():
    assert mt5_executor.should_execute("A+", "A+") is True
    assert mt5_executor.should_execute("A", "A+") is False


def test_unknown_grade_fails_safe():
    # Garbage grade must never execute.
    assert mt5_executor.should_execute("ZZZ", "B") is False


# ── Daily trade cap (daily_limit) ────────────────────────────────────────────────

@pytest.fixture
def fresh_daily(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_limit, "_STATE_PATH", str(tmp_path / "daily.json"))
    return daily_limit


def test_daily_cap_counts_and_blocks(fresh_daily):
    tz = "UTC"
    assert fresh_daily.count_today(tz) == 0
    assert fresh_daily.remaining(1, tz) == 1

    assert fresh_daily.record(tz) == 1
    assert fresh_daily.count_today(tz) == 1
    assert fresh_daily.remaining(1, tz) == 0      # 1/day reached -> no more

    assert fresh_daily.record(tz) == 2            # higher cap still counts up
    assert fresh_daily.remaining(3, tz) == 1


def test_daily_cap_persists_across_reload(fresh_daily):
    fresh_daily.record("UTC")
    # A fresh _load() (simulating a restart) must still see the recorded trade.
    assert fresh_daily.count_today("UTC") == 1


# ── Kill switch (safety pause) ───────────────────────────────────────────────────

@pytest.fixture
def fresh_safety(tmp_path, monkeypatch):
    monkeypatch.setattr(safety, "_STATE_PATH", str(tmp_path / "bot_state.json"))
    return safety


def test_pause_resume(fresh_safety):
    assert fresh_safety.is_paused() is False
    fresh_safety.set_paused(True)
    assert fresh_safety.is_paused() is True
    fresh_safety.set_paused(False)
    assert fresh_safety.is_paused() is False


# ── Daily loss limit (safety.check_daily_loss) ───────────────────────────────────

def test_daily_loss_blocks_at_threshold_and_is_sticky(fresh_safety):
    tz = "UTC"
    # First call of the day seeds the baseline (no loss yet).
    first = fresh_safety.check_daily_loss(100_000, max_loss_pct=2.0, tz_name=tz)
    assert first["blocked"] is False

    # Down exactly 2% -> blocked.
    hit = fresh_safety.check_daily_loss(98_000, max_loss_pct=2.0, tz_name=tz)
    assert hit["blocked"] is True
    assert round(hit["loss_pct"], 2) == 2.0

    # Sticky: even after recovering, the day stays blocked.
    recovered = fresh_safety.check_daily_loss(99_500, max_loss_pct=2.0, tz_name=tz)
    assert recovered["blocked"] is True


def test_daily_loss_not_blocked_above_threshold(fresh_safety):
    tz = "UTC"
    fresh_safety.check_daily_loss(100_000, 2.0, tz)        # seed baseline
    res = fresh_safety.check_daily_loss(99_000, 2.0, tz)   # only -1%
    assert res["blocked"] is False


def test_daily_loss_disabled_when_pct_zero(fresh_safety):
    tz = "UTC"
    fresh_safety.check_daily_loss(100_000, 0, tz)
    res = fresh_safety.check_daily_loss(50_000, 0, tz)     # -50% but limit disabled
    assert res["blocked"] is False
