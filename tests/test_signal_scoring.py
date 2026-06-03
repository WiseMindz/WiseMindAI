"""
Signal scoring + grade tests (signal_utils.evaluate_signal / extract_signal_data_from_text).

These guard the bot's BRAIN: how a Pine/TradingView signal becomes a 0-10 score and an
A+/A/B/C grade. A wrong grade => the wrong trades get executed, so this is money-touching.
"""

from signal_utils import evaluate_signal, extract_signal_data_from_text


# ── v9.25 edge grade path (signal_grade is authoritative, 4-tier preserved) ──────

def test_signal_grade_path_preserves_each_tier():
    for grade, expected_score in [("A+", 9.5), ("A", 7.5), ("B", 5.5), ("C", 3.0)]:
        res = evaluate_signal({"signal_grade": grade})
        assert res["rating"] == grade, f"{grade} must NOT be collapsed"
        assert res["score"] == expected_score
        assert res["pine_scored"] is True


# ── v9.22 Pine quality_score path ────────────────────────────────────────────────

def test_pine_quality_score_uses_explicit_grade():
    res = evaluate_signal({"quality_score": 82, "quality_grade": "A+"})
    assert res["score"] == 8.2          # 82/100 -> 8.2
    assert res["rating"] == "A+"
    assert res["pine_scored"] is True


def test_pine_quality_score_derives_grade_when_absent():
    assert evaluate_signal({"quality_score": 90})["rating"] == "A+"   # >=8.5
    assert evaluate_signal({"quality_score": 75})["rating"] == "A"    # >=7.0
    assert evaluate_signal({"quality_score": 55})["rating"] == "B"    # >=5.0
    assert evaluate_signal({"quality_score": 40})["rating"] == "C"    # <5.0


def test_pine_quality_score_clamped_to_10():
    res = evaluate_signal({"quality_score": 130})
    assert res["score"] == 10.0


# ── Python fallback scoring (older payloads / user messages) ─────────────────────

def test_fallback_strong_t2_amd_is_a_plus():
    res = evaluate_signal({
        "trade": "T2 LONG (AMD)", "after_manipulation": True, "rr": 5.0,
        "session": "London", "swept": "LH", "engulf_body_pct": 0.95,
        "vol_spike": 1.5, "htf_aligned": True,
    })
    assert res["pine_scored"] is False
    assert res["score"] == 9.5
    assert res["rating"] == "A+"


def test_fallback_mid_quality_is_a_tier():
    # 4-tier check: a real "A" must exist between A+ and B in the fallback path.
    res = evaluate_signal({
        "trade": "T2 LONG (AMD)", "after_manipulation": True,
        "rr": 3.0, "session": "London",
    })
    assert res["score"] == 7.0
    assert res["rating"] == "A"


def test_fallback_weak_setup_is_c():
    res = evaluate_signal({"trade": "T1 LONG (1st)", "rr": 2.0})
    assert res["rating"] == "C"


def test_fallback_asia_wide_penalises():
    base = {"trade": "T2 LONG (AMD)", "rr": 4.0, "session": "London"}
    with_warn = dict(base, asia_wide=True)
    assert evaluate_signal(with_warn)["score"] < evaluate_signal(base)["score"]


def test_score_never_negative_or_above_10():
    res = evaluate_signal({"trade": "T1", "rr": 0, "asia_wide": True})
    assert 0.0 <= res["score"] <= 10.0


# ── Text extraction (user messages / OCR) ────────────────────────────────────────

def test_extract_from_natural_text():
    data = extract_signal_data_from_text(
        "tog en T1 long på EURUSD entry 1.085 sl 1.082 tp 1.092 london"
    )
    assert data is not None
    assert data["symbol"] == "EURUSD"
    assert data["side"] == "LONG"
    assert data["entry"] == 1.085
    assert data["sl"] == 1.082
    assert data["tp"] == 1.092
    assert data["session"] == "London"
    assert "T1" in data["trade"]


def test_extract_gold_alias():
    data = extract_signal_data_from_text("short gold entry 2000 sl 2010 tp 1980")
    assert data is not None
    assert data["symbol"] == "XAUUSD"
    assert data["side"] == "SHORT"


def test_extract_returns_none_for_noise():
    assert extract_signal_data_from_text("hej hur mår du idag") is None
    assert extract_signal_data_from_text("") is None
    assert extract_signal_data_from_text(None) is None
