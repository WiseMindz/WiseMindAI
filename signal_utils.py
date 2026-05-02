import re


def evaluate_signal(signal_data: dict) -> dict:
    """
    Evaluerar en signal mot WiseMind-regler och ger score/rating.

    Args:
        signal_data: dict med signalinformation (från webhook, OCR, etc.)

    Returns:
        dict med score (0-10), rating (A+/B/C), förklaring
    """
    score = 0
    reasons = []

    swept = signal_data.get("swept", "").strip().upper()
    if swept and swept not in ["MISSING", "NO", "NONE", ""]:
        score += 2
        reasons.append("Sweep: ✓")
    else:
        reasons.append("Sweep: ✗ (Saknas)")

    displacement = signal_data.get("displacement", "").strip().lower()
    if displacement in ["yes", "true", "1"]:
        score += 2
        reasons.append("Displacement: ✓")
    else:
        reasons.append("Displacement: ✗ (Saknas)")

    pd_zone = signal_data.get("pd_zone", "").strip().upper()
    if pd_zone and pd_zone not in ["MISSING", "NO", "NONE", ""]:
        score += 2
        reasons.append("PD-zone touch: ✓")
    else:
        reasons.append("PD-zone touch: ✗ (Saknas)")

    engulfing = signal_data.get("engulfing", "").strip().lower()
    if engulfing in ["yes", "true", "1"]:
        score += 2
        reasons.append("Engulfing: ✓")
    else:
        reasons.append("Engulfing: ✗ (Saknas)")

    session = signal_data.get("session", "").strip().lower()
    tf = signal_data.get("tf", "").strip().lower()
    valid_sessions = ["london", "ny", "asia"]
    valid_tf = ["5m", "1m"]
    if session in valid_sessions and tf in valid_tf:
        score += 2
        reasons.append("Session/TF: ✓")
    else:
        reasons.append("Session/TF: ✗ (Ogiltig session eller TF)")

    rr = signal_data.get("rr", 0)
    if rr >= 3:
        score += min(1, 10 - score)
        reasons.append("RR: ✓ (≥3:1)")
    elif rr >= 2:
        score += min(0.5, 10 - score)
        reasons.append("RR: ~ (≥2:1)")
    else:
        reasons.append("RR: ✗ (<2:1)")

    if score >= 8:
        rating = "A+"
    elif score >= 6:
        rating = "B"
    else:
        rating = "C"

    explanation = f"Score: {score}/10 ({rating}). " + " | ".join(reasons)

    return {
        "score": score,
        "rating": rating,
        "explanation": explanation,
    }


def extract_signal_data_from_text(text: str) -> dict:
    """
    Försöker extrahera signaldata från fri text (OCR eller användarinput).

    Args:
        text: fri text att analysera

    Returns:
        dict med extraherade signaldata
    """
    data = {}
    text_lower = text.lower()

    symbol_match = re.search(r"\b([a-z]{3,6}(?:usd|eur|jpy|gbp|chf|aud|cad|nzd))\b", text_lower)
    if symbol_match:
        data["symbol"] = symbol_match.group(1).upper()

    if "long" in text_lower:
        data["side"] = "LONG"
    elif "short" in text_lower:
        data["side"] = "SHORT"

    entry_match = re.search(r"entry[:=]?\s*([0-9]+\.?[0-9]*)", text_lower)
    if entry_match:
        data["entry"] = float(entry_match.group(1))

    sl_match = re.search(r"sl[:=]?\s*([0-9]+\.?[0-9]*)", text_lower)
    if sl_match:
        data["sl"] = float(sl_match.group(1))

    tp_match = re.search(r"tp[:=]?\s*([0-9]+\.?[0-9]*)", text_lower)
    if tp_match:
        data["tp"] = float(tp_match.group(1))

    rr_match = re.search(r"rr[:=]?\s*([0-9]+\.?[0-9]*)", text_lower)
    if rr_match:
        data["rr"] = float(rr_match.group(1))

    if "swept" in text_lower or "sweep" in text_lower:
        data["swept"] = "YES"
    if "displacement" in text_lower or "atr" in text_lower:
        data["displacement"] = "yes"
    if "pd" in text_lower or "fvg" in text_lower or "ob" in text_lower:
        data["pd_zone"] = "YES"
    if "engulf" in text_lower:
        data["engulfing"] = "yes"

    if "london" in text_lower:
        data["session"] = "London"
    elif "ny" in text_lower or "new york" in text_lower:
        data["session"] = "NY"
    elif "asia" in text_lower:
        data["session"] = "Asia"

    if "5m" in text_lower:
        data["tf"] = "5m"
    elif "1m" in text_lower:
        data["tf"] = "1m"

    return data
