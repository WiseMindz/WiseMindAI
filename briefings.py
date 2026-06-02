"""
Daily briefings — the proactive layer of the brain.

A self-pacing asyncio scheduler that posts two Claude-written briefs per day to the
Telegram group:
  • Morning (default 08:30 CEST, pre-London): bias/discipline reminder + recent stats + a focus point
  • Evening (default 17:30 CEST, post-NY): honest review of recent performance + one lesson

Uses ONLY real stats (from stats.compute_stats) — Claude is told never to invent news or levels.
"""

import asyncio
import logging
import datetime

logger = logging.getLogger(__name__)


def _now(tz_name: str) -> datetime.datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz_name))
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)


def _seconds_until_next(tz_name: str, times: list) -> tuple:
    """times = [(hour, minute, kind), ...]. Returns (seconds_to_wait, kind)."""
    now = _now(tz_name)
    best = None
    for h, m, kind in times:
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now:
            t = t + datetime.timedelta(days=1)
        if best is None or t < best[0]:
            best = (t, kind)
    return (best[0] - now).total_seconds(), best[1]


async def _send_brief(kind, bot, claude, system_prompt, model, chat_id):
    import stats as _stats
    s = await _stats.compute_stats()
    facts = _stats.build_review_prompt(s)

    if kind == "morning":
        header = "🌅 <b>Morning Brief</b>"
        prompt = (
            "Write a SHORT morning pre-session brief (London opens 09:00 CEST, NY 14:00). "
            "Use ONLY these real stats — do NOT invent news, prices, or levels:\n\n" + facts +
            "\n\nRemind the trader: A+/A/B grades only, max 1 trade today, breakeven at 1.5R. "
            "End with ONE focus point grounded in the stats. Keep it tight and motivating, not generic."
        )
    else:
        header = "🌙 <b>Evening Review</b>"
        prompt = (
            "Write a SHORT evening review. Use ONLY these real stats — do NOT invent anything:\n\n" + facts +
            "\n\nFocus on process over outcome. Give ONE concrete lesson for tomorrow. Keep it tight."
        )

    try:
        resp = await claude.messages.create(
            model=model, max_tokens=500, system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        await bot.send_message(chat_id=chat_id, text=f"{header}\n\n{text}", parse_mode="HTML")
        logger.info(f"📅 Briefing sent: {kind}")
    except Exception as e:
        logger.error(f"Briefing {kind} failed: {type(e).__name__}: {str(e)[:120]}")


async def run_briefings(bot, claude, system_prompt, model, chat_id,
                        tz_name="Europe/Stockholm", morning="08:30", evening="17:30"):
    """Background loop: sleep until the next briefing time, post it, repeat."""
    def _parse(hm, default):
        try:
            h, m = hm.split(":")
            return int(h), int(m)
        except Exception:
            return default
    mh, mm = _parse(morning, (8, 30))
    eh, em = _parse(evening, (17, 30))
    times = [(mh, mm, "morning"), (eh, em, "evening")]

    logger.info(f"📅 Daily briefings scheduler started — {morning} morning / {evening} evening ({tz_name})")
    while True:
        try:
            secs, kind = _seconds_until_next(tz_name, times)
            await asyncio.sleep(secs)
            await _send_brief(kind, bot, claude, system_prompt, model, chat_id)
            await asyncio.sleep(61)  # step past the firing minute so we don't double-send
        except asyncio.CancelledError:
            logger.info("📅 Briefings scheduler stopped")
            raise
        except Exception as e:
            logger.error(f"Briefing loop error: {type(e).__name__}: {str(e)[:120]}")
            await asyncio.sleep(300)
