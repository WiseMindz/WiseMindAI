"""
signal_utils.py — Signal evaluation for WiseMind AI

Receives JSON from Pine v9.22 webhook OR text from user messages.
Scores signals 0-10 and returns A+/B/C rating.

v9.22 SCHEMA (what Pine sends in JSON):
    {
        "secret": "wisemind2026",
        "version": "9.22",
        "symbol": "EURUSD",
        "side": "LONG",
        "trade": "T1 LONG (1st)" | "T1 LONG (2nd)" | "T2 LONG (AMD)",
        "session": "London" | "London+ext" | "NY",
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
        "tf": "5m" | "1m",
        "tf_type": "5m" | "1m",          # v9.22: explicit timeframe type
        "conflict_resolved": false,       # v9.22: HTF/LTF conflict was resolved
        # v9.17 deep signal data (carried forward):
        "displacement_atr": 1.85,
        "engulf_body_pct": 0.92,
        "vol_spike": 1.34,
        "htf_aligned": true,
        # v9.22 Pine-computed quality score (authoritative when present):
        "quality_score": 82,              # int 0-100 (Pine computed)
        "quality_grade": "A+"             # "A+", "B", "C" (Pine computed)
    }

Priority: when quality_score is present (Pine computed), use it directly.
          Fall back to Python scoring when quality_score is absent.
"""

import re
from typing import Optional


# ==================== MAIN EVALUATION FUNCTION ====================

def _normalize_session(raw: str) -> str:
    """Normalise session string for scoring. 'London+ext' → 'london', etc."""
    s = raw.strip().lower()
    if s.startswith("london"):
        return "london"
    if s.startswith("ny") or s.startswith("new york"):
        return "ny"
    if s.startswith("asia"):
        return "asia"
    return s


def evaluate_signal(signal_data: dict) -> dict:
    """
    Score a signal 0-10 based on v9.22 JSON fields.

    v9.22 priority: when Pine sends quality_score (0-100) and quality_grade,
    those are used directly as the authoritative score. Python scoring is the
    fallback for older payloads or manual user messages.

    Returns: {
        "score": 8.2,          # 0-10 (normalised from Pine 0-100 when available)
        "rating": "A+",        # "A+", "B", or "C"
        "explanation": "...",
        "reasons": [...],
        "pine_scored": True    # True when Pine's quality_score was used
    }
    """
    reasons = []

    # ── v9.25: signal_grade from 223-chart edge filters ─────────────────────
    sig_grade = signal_data.get("signal_grade")
    if sig_grade in ("A+", "A", "B", "C"):
        grade_map = {"A+": 9.5, "A": 7.5, "B": 5.5, "C": 3.0}
        score = grade_map.get(sig_grade, 5.0)
        # 4-tier aware: preserve the exact Pine grade (A+/A/B/C) — no collapsing A→B
        rating = sig_grade
        reasons.append(f"v9.25 edge grade: {sig_grade}")
        if signal_data.get("fvg_nearby"):
            reasons.append("✦ FVG nearby")
        if signal_data.get("htf_aligned"):
            reasons.append("✓ HTF aligned")
        if signal_data.get("consolidation"):
            reasons.append("⚠ consolidation")
        explanation = f"v9.25 signal grade: {sig_grade}. " + " | ".join(reasons)
        return {
            "score": score,
            "rating": rating,
            "explanation": explanation,
            "reasons": reasons,
            "pine_scored": True,
        }

    # ── v9.22: Pine authoritative score ──────────────────────────────────────
    raw_pine_score = signal_data.get("quality_score")
    raw_pine_grade = signal_data.get("quality_grade")

    if raw_pine_score is not None:
        try:
            pine_score_100 = int(raw_pine_score)
        except (ValueError, TypeError):
            pine_score_100 = None

        if pine_score_100 is not None:
            score = round(pine_score_100 / 10.0, 1)   # 0-100 → 0-10
            score = max(0.0, min(score, 10.0))

            # Use Pine's grade if present (4-tier A+/A/B/C); else derive from score
            if raw_pine_grade in ("A+", "A", "B", "C"):
                rating = raw_pine_grade
            else:
                rating = ("A+" if score >= 8.5 else "A" if score >= 7.0
                          else "B" if score >= 5.0 else "C")

            reasons.append(f"Pine quality score: {pine_score_100}/100")

            # Annotate conflict_resolved if flagged
            if signal_data.get("conflict_resolved"):
                reasons.append("✓ HTF/LTF conflict resolved")

            # Annotate tf_type
            tf_type = str(signal_data.get("tf_type", "")).lower()
            if tf_type == "1m":
                reasons.append("1m precision entry")
            elif tf_type == "5m":
                reasons.append("5m structure entry")

            explanation = f"Pine score: {pine_score_100}/100 ({rating}). " + " | ".join(reasons)
            return {
                "score": score,
                "rating": rating,
                "explanation": explanation,
                "reasons": reasons,
                "pine_scored": True,
            }

    # ── Fallback: Python scoring (v9.17 and earlier / user messages) ─────────
    score = 0.0

    # --- 1. TRADE TYPE QUALITY (0-3 points) ---
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
    session = _normalize_session(str(signal_data.get("session", "")))
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
    tf_type = str(signal_data.get("tf_type", "")).lower()
    if tf_type == "1m" or "1m" in tf:
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

    # --- 8. ENGULF BODY % (0-0.5 points) ---
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

    # --- 9. VOLUME SPIKE (0-0.5 points) ---
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

    # --- 10. HTF ALIGNMENT (0-0.5 points) ---
    if signal_data.get("htf_aligned") is True:
        score += 0.5
        reasons.append("HTF aligned: +0.5")

    # --- CAP and grade ---
    score = max(0.0, min(score, 10.0))

    # 4-tier grade (A+/A/B/C) to match the indicator
    if score >= 8.5:
        rating = "A+"
    elif score >= 7.0:
        rating = "A"
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
        "pine_scored": False,
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
