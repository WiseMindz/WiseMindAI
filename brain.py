"""
brain.py — the WiseMind LEARNING BRAIN (server-side).

Turns the COMPLETE trade record (trade_results, now filled by both Pine results and
broker reconciliation) into learning:
  • rolling stats grouped by session / symbol / trade-type (T1/T2) / month
  • plain-English recommendations — "what wins / what leaks"

Pure functions (compute_brain / recommendations) are unit-tested; the DB read +
Telegram formatting are thin wrappers around them.
"""

import aiosqlite
from database import DB_PATH


def _wr(wins: int, losses: int) -> float:
    decided = wins + losses
    return round(wins / decided * 100, 1) if decided else 0.0


def _group(rows: list, key: str) -> dict:
    """Group outcome rows by a key → {bucket: {n,wins,losses,be,r,wr,exp}}."""
    g: dict = {}
    for r in rows:
        bucket = str((r.get(key) or "?")).strip() or "?"
        res = str(r.get("result") or "").upper()
        d = g.setdefault(bucket, {"n": 0, "wins": 0, "losses": 0, "be": 0, "r": 0.0})
        d["n"] += 1
        if res == "WIN":
            d["wins"] += 1
        elif res == "LOSS":
            d["losses"] += 1
        elif res == "BE":
            d["be"] += 1
        try:
            d["r"] += float(r.get("rr_achieved") or 0)
        except (TypeError, ValueError):
            pass
    for d in g.values():
        d["wr"] = _wr(d["wins"], d["losses"])
        d["r"] = round(d["r"], 1)
        d["exp"] = round(d["r"] / d["n"], 2) if d["n"] else 0.0
    return g


def _month_key(ts: str) -> str:
    # ts is ISO "YYYY-MM-DD..." → "YYYY-MM"
    return (ts or "")[:7] or "?"


def compute_brain(rows: list) -> dict:
    """
    rows = list of dicts each with: result, rr_achieved, session, symbol,
           trade_type, timestamp. Returns grouped learning + totals.
    """
    for r in rows:
        r["_month"] = _month_key(r.get("timestamp", ""))

    total = len(rows)
    wins = sum(1 for r in rows if str(r.get("result", "")).upper() == "WIN")
    losses = sum(1 for r in rows if str(r.get("result", "")).upper() == "LOSS")
    be = sum(1 for r in rows if str(r.get("result", "")).upper() == "BE")
    rr = [float(r["rr_achieved"]) for r in rows if r.get("rr_achieved") is not None]
    total_r = round(sum(rr), 1) if rr else 0.0

    return {
        "total": total, "wins": wins, "losses": losses, "be": be,
        "win_rate": _wr(wins, losses),
        "expectancy": round(total_r / total, 2) if total else 0.0,
        "total_r": total_r,
        "by_session": _group(rows, "session"),
        "by_symbol": _group(rows, "symbol"),
        "by_type": _group(rows, "trade_type"),
        "by_month": _group(rows, "_month"),
    }


def recommendations(b: dict, min_sample: int = 5) -> list:
    """Plain-English insights. Only fire on buckets with a real sample (>= min_sample)."""
    out = []
    if b["total"] < min_sample:
        out.append(f"📊 Only {b['total']} completed trades recorded — need ≥{min_sample} per bucket "
                   "before the brain trusts a pattern. Keep recording.")
        return out

    # Best / worst session, symbol, type by expectancy (R/trade) with enough sample
    for label, group in (("session", b["by_session"]), ("symbol", b["by_symbol"]), ("type", b["by_type"])):
        sized = {k: d for k, d in group.items() if d["n"] >= min_sample and k != "?"}
        if len(sized) >= 2:
            best = max(sized.items(), key=lambda kv: kv[1]["exp"])
            worst = min(sized.items(), key=lambda kv: kv[1]["exp"])
            if best[0] != worst[0]:
                out.append(f"✅ Best {label}: <b>{best[0]}</b> ({best[1]['exp']}R/trade, "
                           f"{best[1]['wr']}% WR, n={best[1]['n']}).")
                if worst[1]["exp"] < 0:
                    out.append(f"🔻 Leaking {label}: <b>{worst[0]}</b> ({worst[1]['exp']}R/trade, "
                               f"{worst[1]['wr']}% WR, n={worst[1]['n']}) — consider tightening or skipping.")

    if b["win_rate"] and b["win_rate"] < 50 and b["expectancy"] <= 0:
        out.append(f"⚠️ Overall WR {b['win_rate']}% with {b['expectancy']}R expectancy — process review needed.")
    elif b["expectancy"] > 0:
        out.append(f"🟢 Overall edge positive: {b['expectancy']}R/trade across {b['total']} trades.")

    if not out:
        out.append("📊 Recording, but no bucket yet has a big enough sample for a confident call.")
    return out


def format_brain(b: dict) -> str:
    """Telegram HTML summary of the brain."""
    if b["total"] == 0:
        return ("🧠 <b>WiseMind Brain</b>\nNo completed trades recorded yet.\n"
                "<i>Fills + outcomes accumulate here as trades close (Pine results + broker reconciliation).</i>")
    msg = "🧠 <b>WiseMind Brain</b>\n"
    msg += f"Recorded: <b>{b['total']}</b>  ·  {b['wins']}W/{b['losses']}L/{b['be']}BE  ·  "
    msg += f"WR <b>{b['win_rate']}%</b>  ·  Exp <b>{b['expectancy']}R</b>  ·  Total <b>{b['total_r']}R</b>\n"
    for title, group in (("By session", b["by_session"]), ("By symbol", b["by_symbol"]),
                         ("By type", b["by_type"]), ("By month", b["by_month"])):
        if group:
            msg += f"\n<b>{title}:</b>\n"
            for k, d in sorted(group.items()):
                msg += f"  {k}: {d['wr']}% · {d['exp']}R · {d['wins']}W/{d['losses']}L (n={d['n']})\n"
    msg += "\n<b>🧠 Learnings:</b>\n" + "\n".join(recommendations(b))
    return msg


async def load_outcomes(limit: int = 2000) -> list:
    """Read completed outcomes from trade_results for the brain."""
    rows = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT result, rr_achieved, session, symbol, trade_type, timestamp "
                "FROM trade_results ORDER BY timestamp DESC LIMIT ?", (limit,)
            ) as cur:
                rows = [dict(r) async for r in cur]
    except Exception:
        rows = []
    return rows


async def get_brain() -> dict:
    return compute_brain(await load_outcomes())
