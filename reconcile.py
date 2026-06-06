"""
reconcile.py — broker-truth reconciliation (the foundation of the learning brain).

The bot used to only learn from Pine's WIN/LOSS webhooks, so bot-managed exits
(24h expiry, breakeven stop) were NEVER recorded → invisible in /stats.

This module READS the MetaAPI deal history (read-only — never places/touches trades),
finds every CLOSED position, computes its real outcome (WIN/LOSS/BE), real exit price,
realized P&L and R, and records it into trade_results (source="broker"). De-duped by
position_id so a position is recorded once.

Pure logic (summarize_closed_positions / _parse_comment) is unit-tested with mock deals.
"""

import re
import logging
import datetime

logger = logging.getLogger(__name__)

_BE_EPS = 0.01  # realized P&L within ±this (account currency) counts as breakeven


def _parse_comment(comment: str) -> tuple:
    """Bot sets order comment 'WiseMind <session> <grade>' → pull session + grade."""
    c = str(comment or "")
    session = ""
    for s in ("London", "NY", "Asia"):
        if s.lower() in c.lower():
            session = s
            break
    gm = re.search(r"(A\+|\bA\b|\bB\b|\bC\b)", c)
    grade = gm.group(1) if gm else ""
    return session, grade


def _iso(t) -> str:
    if isinstance(t, datetime.datetime):
        return t.isoformat()
    return str(t or "")


def summarize_closed_positions(deals: list, risk_by_position: dict = None,
                               fallback_risk: float = 0.0, eps: float = _BE_EPS) -> list:
    """
    Pure: group raw MetaAPI deals by positionId, return one outcome dict per CLOSED
    position. A position is closed once it has an OUT deal.
    """
    risk_by_position = risk_by_position or {}
    by_pos: dict = {}
    for d in deals or []:
        pid = str(d.get("positionId") or d.get("position_id") or "")
        if not pid:
            continue
        by_pos.setdefault(pid, []).append(d)

    out = []
    for pid, ds in by_pos.items():
        outs = [d for d in ds if "OUT" in str(d.get("entryType", "")).upper()]
        if not outs:
            continue  # still open — skip
        ins = [d for d in ds if str(d.get("entryType", "")).upper() == "DEAL_ENTRY_IN"]
        in_deal = ins[0] if ins else None
        ref = in_deal or outs[-1]
        last_out = outs[-1]

        pnl = 0.0
        for d in ds:
            for fld in ("profit", "commission", "swap"):
                try:
                    pnl += float(d.get(fld, 0) or 0)
                except (TypeError, ValueError):
                    pass

        result = "WIN" if pnl > eps else "LOSS" if pnl < -eps else "BE"
        side = "LONG" if "BUY" in str(ref.get("type", "")).upper() else "SHORT"
        session, grade = _parse_comment(ref.get("comment") or ref.get("brokerComment") or "")
        risk = risk_by_position.get(pid, fallback_risk)
        rr = round(pnl / risk, 2) if risk and risk > 0 else 0.0

        out.append({
            "position_id": pid,
            "symbol": ref.get("symbol", ""),
            "direction": side.lower(),
            "result": result,
            "entry": float(in_deal.get("price", 0) or 0) if in_deal else 0.0,
            "exit_price": float(last_out.get("price", 0) or 0),
            "profit": round(pnl, 2),
            "rr_achieved": rr,
            "session": session,
            "grade": grade,
            "timestamp": _iso(last_out.get("time")),
        })
    return out


async def reconcile_once(connection, get_recorded_ids, save_result,
                         risk_by_position: dict = None, lookback_hours: float = 48.0) -> int:
    """
    One reconciliation pass (read-only). Returns the number of NEW outcomes recorded.
      connection       — MetaAPI RPC connection (read-only use)
      get_recorded_ids — async () -> set[str] of position_ids already in trade_results
      save_result      — async (summary_dict) -> None  (writes one broker outcome)
    """
    if connection is None:
        return 0
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(hours=lookback_hours)
    try:
        resp = await connection.get_deals_by_time_range(start, end)
    except Exception as e:
        logger.error(f"reconcile: deal fetch failed: {type(e).__name__}: {str(e)[:120]}")
        return 0

    deals = resp.get("deals", []) if isinstance(resp, dict) else getattr(resp, "deals", resp) or []
    summaries = summarize_closed_positions(deals, risk_by_position or {})
    try:
        recorded = await get_recorded_ids()
    except Exception:
        recorded = set()

    n = 0
    for s in summaries:
        if s["position_id"] in recorded:
            continue
        try:
            await save_result(s)
            n += 1
        except Exception as e:
            logger.error(f"reconcile: save failed for {s.get('position_id')}: {str(e)[:120]}")
    if n:
        logger.info(f"🧠 reconcile: recorded {n} new broker outcome(s)")
    return n
