"""
signal_utils.py — Signal evaluation for WiseMind AI

Receives JSON from Pine v9.17 webhook OR text from user messages.
Scores signals 0-10 and returns A+/B/C rating.

v9.17 SCHEMA (what Pine sends in JSON):
    {
        "secret": "wisemind2026",
        "symbol": "EURUSD",
        "side": "LONG",
        "trade": "T1 LONG (1st)" | "T1 LONG (2nd)" | "T2 LONG (AMD)",
        "session": "London" | "NY",
        "profile": "EUR" | "XAU" | "CUSTOM",
        "entry": 1.16920,
        "sl": 1.16860,
        "sl_source": "engulf",
        "tp": 1.17430,
        "tp_source": "PDH",
        "rr": 5.0,
        "swept": "AL" | "AH" | "LH" | "LL",
        "after_manipulation": false,
        "asia_wide": false,
        "tf": "5m" or "5m 1m-V2",
        # v9.17 NEW deep signal data:
        "displacement_atr": 1.85,        # 1.85× ATR (T2: actual; T1: candle range as proxy)
        "engulf_body_pct": 0.92,         # 92% body
        "vol_spike": 1.34,               # 34% over 20-bar avg
        "htf_aligned": true              # HTF bias matches direction
    }
"""

import re
from typing import Optional


# ==================== MAIN EVALUATION FUNCTION ====================

def evaluate_signal(signal_data: dict) -> dict:
    """
    Score a signal 0-10 based on v9.17 JSON fields.

    Returns: {
        "score": 8.5,
        "rating": "A+",
        "explanation": "T2 AMD +3 | After manipulation +1.5 | RR 5.0 +2 | ...",
        "reasons": [...]  # list of breakdown strings
    }
    """
    score = 0.0
    reasons = []

    # --- 1. TRADE TYPE QUALITY (0-3 points) ---
    # T2 AMD is the safest (4-layer protected: sweep + displacement + retrace + PD touch)
    # T1 2nd is safer than T1 1st (waits for stop-hunt)
    trade = str(signal_data.get("trade", "")).upper()
    if "T2" in trade and "AMD" in trade:
        score += 3
        reasons.append("T2 AMD (4-layer protected): +3")
    elif "T1" in trade and "2ND" in trade:
        score += 2.5
        reasons.append("T1 2nd entry (post-manipulation): +2.5")
    elif "T1" in trade and "1ST" in trade:
        score += 1.5
        reasons.append("T1 1st entry (aggressive): +1.5")
    elif "T1" in trade or "T2" in trade:
        score += 1.5
        reasons.append("Generic T1/T2: +1.5")

    # --- 2. AFTER MANIPULATION BONUS (0-1.5 points) ---
    # Stop-hunters already triggered — entry is safer
    if signal_data.get("after_manipulation") is True:
        score += 1.5
        reasons.append("After manipulation wick: +1.5")

    # --- 3. RISK-REWARD (0-2 points) ---
    try:
        rr = float(signal_data.get("rr", 0) or 0)
    except (ValueError, TypeError):
        rr = 0
    if rr >= 4:
        score += 2
        reasons.append(f"RR {rr:.1f} (excellent): +2")
    elif rr >= 3:
        score += 1.5
        reasons.append(f"RR {rr:.1f} (good): +1.5")
    elif rr >= 2.5:
        score += 1
        reasons.append(f"RR {rr:.1f} (acceptable): +1")
    elif rr >= 2:
        score += 0.5
        reasons.append(f"RR {rr:.1f} (low): +0.5")
    elif rr > 0:
        reasons.append(f"RR {rr:.1f} (too low): +0")

    # --- 4. SESSION QUALITY (0-1 point) ---
    session = str(signal_data.get("session", "")).strip().lower()
    if session == "london":
        score += 1
        reasons.append("London session: +1")
    elif session == "ny":
        score += 0.7
        reasons.append("NY session: +0.7")

    # --- 5. ASIA WIDE WARNING (0 to -1 points) ---
    if signal_data.get("asia_wide") is True:
        score -= 1
        reasons.append("⚠ Asia wide warning: -1")

    # --- 6. 1m PRECISION BONUS (0-0.5 points) ---
    tf = str(signal_data.get("tf", "")).lower()
    if "1m" in tf or "{1m" in tf:
        score += 0.5
        reasons.append("1m precision entry: +0.5")

    # --- 7. SWEEP SOURCE QUALITY (0-0.5 points) ---
    swept = str(signal_data.get("swept", "")).strip().upper()
    if swept in ["LH", "LL"]:
        score += 0.5
        reasons.append(f"London level swept ({swept}): +0.5")
    elif swept in ["AH", "AL"]:
        score += 0.3
        reasons.append(f"Asia level swept ({swept}): +0.3")

    # --- 8. v9.17 DEEP DATA: ENGULF BODY % (0-0.5 points) ---
    try:
        engulf_pct = float(signal_data.get("engulf_body_pct", 0) or 0)
    except (ValueError, TypeError):
        engulf_pct = 0
    if engulf_pct >= 0.95:
        score += 0.5
        reasons.append(f"Engulf {engulf_pct:.0%} (very strong): +0.5")
    elif engulf_pct >= 0.90:
        score += 0.3
        reasons.append(f"Engulf {engulf_pct:.0%} (strong): +0.3")
    elif engulf_pct >= 0.85:
        score += 0.1
        reasons.append(f"Engulf {engulf_pct:.0%}: +0.1")

    # --- 9. v9.17 DEEP DATA: VOLUME SPIKE (0-0.5 points) ---
    try:
        vol_spike = float(signal_data.get("vol_spike", 0) or 0)
    except (ValueError, TypeError):
        vol_spike = 0
    if vol_spike >= 1.5:
        score += 0.5
        reasons.append(f"Vol spike {vol_spike:.1f}× (strong): +0.5")
    elif vol_spike >= 1.2:
        score += 0.3
        reasons.append(f"Vol spike {vol_spike:.1f}×: +0.3")

    # --- 10. v9.17 DEEP DATA: HTF ALIGNMENT (0-0.5 points) ---
    if signal_data.get("htf_aligned") is True:
        score += 0.5
        reasons.append("HTF aligned: +0.5")

    # --- CAP between 0-10 ---
    score = max(0, min(score, 10))

    # --- DETERMINE RATING ---
    if score >= 7.5:
        rating = "A+"
    elif score >= 5:
        rating = "B"
    else:
        rating = "C"

    explanation = f"Score: {score:.1f}/10 ({rating}). " + " | ".join(reasons)

    return {
        "score": round(score, 1),
        "rating": rating,
        "explanation": explanation,
        "reasons": reasons,
    }


# ==================== TEXT EXTRACTION (for user messages / OCR) ====================

def extract_signal_data_from_text(text: str) -> Optional[dict]:
    """
    Try to extract signal fields from natural-language text (user messages, OCR).
    Returns None if nothing useful was found, else dict matching v9.17 schema.

    Accepts naturally written messages like:
      "tog en T1 long på EURUSD entry 1.085 sl 1.082 tp 1.092 london"
    """
    if not text or not isinstance(text, str):
        return None

    text_lower = text.lower()
    data = {}

    # Symbol — common forex pairs + gold
    symbol_match = re.search(
        r"\b(eurusd|gbpusd|usdjpy|usdchf|audusd|nzdusd|usdcad|xauusd|gold|btcusd|nas100|us30|spx500)\b",
        text_lower
    )
    if symbol_match:
        sym = symbol_match.group(1).upper()
        data["symbol"] = "XAUUSD" if sym == "GOLD" else sym

    # Side — long/short or buy/sell
    if re.search(r"\b(long|buy|köp|köpa)\b", text_lower):
        data["side"] = "LONG"
    elif re.search(r"\b(short|sell|sälj|sälja)\b", text_lower):
        data["side"] = "SHORT"

    # Trade type — T1 / T2
    if re.search(r"\bt2\b|amd", text_lower):
        side = data.get("side", "LONG")
        data["trade"] = f"T2 {side} (AMD)"
    elif re.search(r"\bt1\b", text_lower):
        side = data.get("side", "LONG")
        is_2nd = "2nd" in text_lower or "andra" in text_lower
        data["trade"] = f"T1 {side} ({'2nd' if is_2nd else '1st'})"

    # Session
    if "london" in text_lower:
        data["session"] = "London"
    elif "ny" in text_lower or "new york" in text_lower:
        data["session"] = "NY"
    elif "asia" in text_lower:
        data["session"] = "Asia"

    # Numeric fields — entry / sl / tp / rr
    for field, pattern in [
        ("entry", r"entry\s*[:=]?\s*([0-9]+\.?[0-9]*)"),
        ("sl",    r"sl\s*[:=]?\s*([0-9]+\.?[0-9]*)"),
        ("tp",    r"tp\s*[:=]?\s*([0-9]+\.?[0-9]*)"),
        ("rr",    r"rr\s*[:=]?\s*([0-9]+\.?[0-9]*)"),
    ]:
        m = re.search(pattern, text_lower)
        if m:
            try:
                data[field] = float(m.group(1))
            except ValueError:
                pass

    # Sweep source — accept LH/LL/AH/AL or descriptive
    if re.search(r"\b(swept|sweep)\s*(lh|al|ah|ll)\b", text_lower):
        m = re.search(r"\b(swept|sweep)\s*(lh|al|ah|ll)\b", text_lower)
        data["swept"] = m.group(2).upper()
    elif "swept asia high" in text_lower or "sweep asia high" in text_lower:
        data["swept"] = "AH"
    elif "swept asia low" in text_lower or "sweep asia low" in text_lower:
        data["swept"] = "AL"
    elif "swept london high" in text_lower or "sweep london high" in text_lower:
        data["swept"] = "LH"
    elif "swept london low" in text_lower or "sweep london low" in text_lower:
        data["swept"] = "LL"

    # Manipulation flag
    if "after manipulation" in text_lower or "post manipulation" in text_lower or "manip" in text_lower:
        data["after_manipulation"] = True

    # TF — 5m / 1m / 15m
    if "1m" in text_lower or "1 min" in text_lower:
        data["tf"] = "1m"
    elif "5m" in text_lower or "5 min" in text_lower:
        data["tf"] = "5m"
    elif "15m" in text_lower:
        data["tf"] = "15m"

    # Return None if we got nothing useful (no symbol, no side, no entry)
    if not data.get("symbol") and not data.get("side") and not data.get("entry"):
        return None

    return data
