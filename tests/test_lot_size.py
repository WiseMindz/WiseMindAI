"""
Lot-size calculation tests (webhook_handler.calculate_lot_size + pip helpers).

This is the most directly money-touching pure function in the bot: it decides how
many lots get sent to the broker. A wrong lot = wrong risk on a real account.
"""

import webhook_handler
from webhook_handler import calculate_lot_size, get_pip_value, get_pip_size

# The pure lot-math tests below test the RAW formula with no $-risk cap. The live safety
# cap (MAX_RISK_DOLLARS) is verified separately in test_risk_cap_* at the bottom.
webhook_handler.MAX_RISK_DOLLARS = 0


def test_eurusd_one_percent_risk():
    # $100k, 1% risk = $1000. SL 50 pips. pip value $10 => 1000/(50*10) = 2.0 lots.
    res = calculate_lot_size("EURUSD", entry=1.1000, sl=1.0950, balance=100_000, risk_pct=1.0)
    assert res["sl_pips"] == 50.0
    assert res["risk_dollars"] == 1000.0
    assert res["lot"] == 2.0


def test_xauusd_lot():
    # $100k, 1% = $1000. SL = $10 move, pip size 0.10 => 100 pips. pip value $10 => 1.0 lot.
    res = calculate_lot_size("XAUUSD", entry=2000.0, sl=1990.0, balance=100_000, risk_pct=1.0)
    assert res["sl_pips"] == 100.0
    assert res["lot"] == 1.0


def test_usdjpy_lot_rounding():
    # pip size 0.01, pip value 9.5. SL 0.50 => 50 pips. 1000/(50*9.5) = 2.105 -> 2.11.
    res = calculate_lot_size("USDJPY", entry=150.00, sl=149.50, balance=100_000, risk_pct=1.0)
    assert res["sl_pips"] == 50.0
    assert res["lot"] == 2.11


def test_risk_scales_lot_linearly():
    half = calculate_lot_size("EURUSD", 1.1000, 1.0950, 100_000, 0.5)["lot"]
    full = calculate_lot_size("EURUSD", 1.1000, 1.0950, 100_000, 1.0)["lot"]
    assert full == 2.0 and half == 1.0


def test_zero_sl_distance_is_safe():
    # entry == sl would divide by zero — must return lot 0, never crash.
    res = calculate_lot_size("EURUSD", entry=1.1000, sl=1.1000, balance=100_000, risk_pct=1.0)
    assert res["lot"] == 0


def test_pip_helpers_handle_broker_suffix():
    # A different broker may send EURUSD.r / XAUUSD.r — must map to the bare symbol.
    assert get_pip_value("EURUSD.r") == get_pip_value("EURUSD") == 10.0
    assert get_pip_size("XAUUSD.r") == get_pip_size("XAUUSD") == 0.10


def test_unknown_symbol_uses_safe_defaults():
    assert get_pip_value("BTCUSD") == 10.0
    assert get_pip_size("BTCUSD") == 0.0001


def test_risk_cap_overrides_oversized_risk():
    # The danger case: balance/risk would risk $2000, but the $500 cap MUST force $500.
    webhook_handler.MAX_RISK_DOLLARS = 500
    try:
        res = calculate_lot_size("EURUSD", entry=1.1000, sl=1.0950, balance=100_000, risk_pct=2.0)
        assert res["risk_dollars"] == 500.0          # capped down from $2000
        assert res["lot"] == 1.0                       # 500/(50*10) = 1.0, not 4.0
    finally:
        webhook_handler.MAX_RISK_DOLLARS = 0


def test_risk_cap_does_not_inflate_when_under():
    # Cap must never RAISE risk — a $500 trade under a $500 cap stays $500.
    webhook_handler.MAX_RISK_DOLLARS = 500
    try:
        res = calculate_lot_size("EURUSD", entry=1.1000, sl=1.0950, balance=50_000, risk_pct=1.0)
        assert res["risk_dollars"] == 500.0
        assert res["lot"] == 1.0
    finally:
        webhook_handler.MAX_RISK_DOLLARS = 0
