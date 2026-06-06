"""Learning-brain tests — pure grouping + recommendation logic."""

from brain import compute_brain, recommendations

ROWS = [
    {"result": "WIN",  "rr_achieved": 2.0,  "session": "London", "symbol": "EURUSD", "trade_type": "T2", "timestamp": "2026-06-01T10:00:00"},
    {"result": "LOSS", "rr_achieved": -1.0, "session": "NY",     "symbol": "XAUUSD", "trade_type": "T1", "timestamp": "2026-06-02T15:00:00"},
    {"result": "WIN",  "rr_achieved": 3.0,  "session": "London", "symbol": "EURUSD", "trade_type": "T2", "timestamp": "2026-05-20T10:00:00"},
    {"result": "BE",   "rr_achieved": 0.0,  "session": "London", "symbol": "EURUSD", "trade_type": "T1", "timestamp": "2026-06-03T10:00:00"},
]


def test_totals():
    b = compute_brain(ROWS)
    assert b["total"] == 4 and b["wins"] == 2 and b["losses"] == 1 and b["be"] == 1
    assert b["win_rate"] == 66.7          # 2 / (2+1)
    assert b["total_r"] == 4.0            # 2 - 1 + 3 + 0
    assert b["expectancy"] == 1.0         # 4.0 / 4


def test_grouping():
    b = compute_brain(ROWS)
    assert b["by_session"]["London"]["n"] == 3
    assert b["by_session"]["NY"]["losses"] == 1
    assert "2026-06" in b["by_month"] and "2026-05" in b["by_month"]
    assert b["by_type"]["T2"]["wins"] == 2


def test_recommendations_need_sample():
    b = compute_brain(ROWS)
    recs = recommendations(b, min_sample=5)
    assert recs and any("recorded" in r.lower() or "trades" in r.lower() for r in recs)


def test_empty_is_safe():
    b = compute_brain([])
    assert b["total"] == 0 and b["win_rate"] == 0.0
    assert recommendations(b)  # returns a message, never crashes
