"""
Trade stats engine — the bot's MEMORY/LEARNING foundation.

Reads outcomes from the `trade_results` table (populated by Pine v9.23+ trade_result
webhooks) and computes performance stats: win rate, expectancy, breakdowns by
session and symbol, recent streak. Used by /stats (numbers) and /review (Claude
analysis). On Railway the DB lives on the /data volume so history accumulates.
"""

import aiosqlite
from database import DB_PATH


async def compute_stats(limit_recent: int = 10) -> dict:
    """Aggregate trade_results into a stats dict. Empty-safe."""
    rows = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT symbol, direction, trade_type, session, result, "
                "rr_planned, rr_achieved, timestamp FROM trade_results "
                "ORDER BY timestamp ASC"
            ) as cur:
                rows = [dict(r) async for r in cur]
    except Exception:
        rows = []

    total = len(rows)
    wins = sum(1 for r in rows if (r.get("result") or "").upper() == "WIN")
    losses = sum(1 for r in rows if (r.get("result") or "").upper() == "LOSS")
    be = sum(1 for r in rows if (r.get("result") or "").upper() == "BE")
    decided = wins + losses
    win_rate = round(wins / decided * 100, 1) if decided else 0.0

    rr_vals = [float(r["rr_achieved"]) for r in rows if r.get("rr_achieved") is not None]
    expectancy = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else 0.0   # avg R per trade
    total_r = round(sum(rr_vals), 1) if rr_vals else 0.0

    def _group(key: str) -> dict:
        g = {}
        for r in rows:
            k = (r.get(key) or "?").strip() or "?"
            res = (r.get("result") or "").upper()
            d = g.setdefault(k, {"n": 0, "wins": 0, "losses": 0})
            d["n"] += 1
            if res == "WIN":
                d["wins"] += 1
            elif res == "LOSS":
                d["losses"] += 1
        for k, d in g.items():
            dec = d["wins"] + d["losses"]
            d["wr"] = round(d["wins"] / dec * 100, 1) if dec else 0.0
        return g

    recent = [(r.get("result") or "?").upper() for r in rows[-limit_recent:]]

    return {
        "total": total, "wins": wins, "losses": losses, "be": be,
        "win_rate": win_rate, "expectancy": expectancy, "total_r": total_r,
        "by_session": _group("session"),
        "by_symbol": _group("symbol"),
        "recent": recent,
    }


def format_stats(s: dict) -> str:
    """Telegram HTML summary of the stats dict."""
    if s["total"] == 0:
        return ("📊 <b>Stats</b>\nNo completed trades logged yet.\n"
                "<i>Stats build as trade results come in from the indicator.</i>")

    emoji = {"WIN": "🟢", "LOSS": "🔴", "BE": "🟡"}
    streak = " ".join(emoji.get(r, "⚪") for r in s["recent"])

    msg = "📊 <b>WiseMind Stats</b>\n"
    msg += f"Trades: <b>{s['total']}</b>  ·  {s['wins']}W / {s['losses']}L / {s['be']}BE\n"
    msg += f"Win rate: <b>{s['win_rate']}%</b>  ·  Expectancy: <b>{s['expectancy']}R</b>/trade  ·  Total: <b>{s['total_r']}R</b>\n"
    if streak:
        msg += f"Recent: {streak}\n"

    if s["by_session"]:
        msg += "\n<b>By session:</b>\n"
        for k, d in sorted(s["by_session"].items()):
            msg += f"  {k}: {d['wr']}% ({d['wins']}W/{d['losses']}L, n={d['n']})\n"
    if s["by_symbol"]:
        msg += "\n<b>By symbol:</b>\n"
        for k, d in sorted(s["by_symbol"].items()):
            msg += f"  {k}: {d['wr']}% ({d['wins']}W/{d['losses']}L, n={d['n']})\n"
    return msg


def build_review_prompt(s: dict) -> str:
    """Compact factual summary for Claude to analyze (no invented data)."""
    lines = [
        f"Total completed trades: {s['total']} ({s['wins']}W/{s['losses']}L/{s['be']}BE)",
        f"Win rate: {s['win_rate']}%  Expectancy: {s['expectancy']}R/trade  Total: {s['total_r']}R",
        f"Recent (oldest→newest): {', '.join(s['recent']) or 'none'}",
        "By session: " + ("; ".join(f"{k} {d['wr']}% n={d['n']}" for k, d in s["by_session"].items()) or "none"),
        "By symbol: " + ("; ".join(f"{k} {d['wr']}% n={d['n']}" for k, d in s["by_symbol"].items()) or "none"),
    ]
    return "\n".join(lines)
