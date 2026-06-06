"""Reconciliation tests — pure deal-summarisation logic (no live MetaAPI needed)."""

from reconcile import summarize_closed_positions, _parse_comment


def _deal(pid, entry_type, dtype, price, profit, comment=""):
    return {"positionId": pid, "entryType": entry_type, "type": dtype, "price": price,
            "profit": profit, "symbol": "EURUSD", "comment": comment, "time": "2026-06-05T12:00:00"}


DEALS = [
    _deal("P1", "DEAL_ENTRY_IN", "DEAL_TYPE_BUY", 1.10, 0, "WiseMind London A"),
    _deal("P1", "DEAL_ENTRY_OUT", "DEAL_TYPE_SELL", 1.11, 500, "WiseMind London A"),
    _deal("P2", "DEAL_ENTRY_IN", "DEAL_TYPE_SELL", 1.20, 0, "WiseMind NY B"),
    _deal("P2", "DEAL_ENTRY_OUT", "DEAL_TYPE_BUY", 1.21, -470, "WiseMind NY B"),
    _deal("P3", "DEAL_ENTRY_IN", "DEAL_TYPE_BUY", 1.30, 0, "WiseMind London C"),  # OPEN
]


def test_only_closed_positions_summarised():
    res = summarize_closed_positions(DEALS, {"P1": 500.0, "P2": 470.0})
    assert {r["position_id"] for r in res} == {"P1", "P2"}  # P3 still open → skipped


def test_outcomes_direction_and_R():
    res = {r["position_id"]: r for r in summarize_closed_positions(DEALS, {"P1": 500.0, "P2": 470.0})}
    assert res["P1"]["result"] == "WIN" and res["P1"]["direction"] == "long" and res["P1"]["rr_achieved"] == 1.0
    assert res["P2"]["result"] == "LOSS" and res["P2"]["direction"] == "short" and res["P2"]["rr_achieved"] == -1.0
    assert res["P1"]["session"] == "London" and res["P1"]["grade"] == "A"
    assert res["P1"]["exit_price"] == 1.11 and res["P1"]["profit"] == 500.0


def test_breakeven_classification():
    deals = [_deal("PB", "DEAL_ENTRY_IN", "DEAL_TYPE_BUY", 1.1, 0),
             _deal("PB", "DEAL_ENTRY_OUT", "DEAL_TYPE_SELL", 1.1, 0.0)]
    assert summarize_closed_positions(deals, {})[0]["result"] == "BE"


def test_R_zero_when_no_risk_known():
    deals = [_deal("PX", "DEAL_ENTRY_IN", "DEAL_TYPE_BUY", 1.1, 0),
             _deal("PX", "DEAL_ENTRY_OUT", "DEAL_TYPE_SELL", 1.2, 300)]
    assert summarize_closed_positions(deals, {})[0]["rr_achieved"] == 0.0  # no risk map → R unknown


def test_parse_comment():
    assert _parse_comment("WiseMind London A+") == ("London", "A+")
    assert _parse_comment("WiseMind NY B") == ("NY", "B")
    assert _parse_comment("WiseMind Asia A") == ("Asia", "A")
    assert _parse_comment("") == ("", "")
