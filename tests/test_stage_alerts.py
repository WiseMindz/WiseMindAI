"""
Stage-by-stage setup-alert tests (webhook_handler.handle_stage).

Guards the live play-by-play: only the right stages broadcast, the secret is
enforced, identical alerts are deduped, and 'fired' never leaks into the stage feed.
Telegram sending is stubbed so no real message is ever sent.
"""

import pytest
from fastapi import HTTPException

import webhook_handler


class _FakeBot:
    """Stand-in for the telegram Bot (which uses __slots__ and can't be patched in place)."""
    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        self.sent.append(kwargs)
        return None


@pytest.fixture
def wh(monkeypatch):
    """Fresh handler state + a stubbed Telegram bot that records sent messages."""
    webhook_handler._stage_last.clear()
    fake = _FakeBot()
    monkeypatch.setattr(webhook_handler, "telegram_bot", fake)
    return webhook_handler, fake.sent


SECRET = "wisemind2026"


async def test_bad_secret_rejected(wh):
    handler, sent = wh
    with pytest.raises(HTTPException) as exc:
        await handler.handle_stage({"secret": "wrong", "stage": "sweep", "symbol": "EURUSD"})
    assert exc.value.status_code == 401
    assert sent == []


async def test_sweep_posts_clean_line(wh):
    handler, sent = wh
    res = await handler.handle_stage({
        "secret": SECRET, "stage": "sweep", "symbol": "EURUSD",
        "session": "London", "detail": "AL swept",
    })
    assert res["status"] == "ok"
    assert len(sent) == 1
    text = sent[0]["text"]
    assert "EURUSD" in text and "🌊" in text and "London" in text


async def test_fired_stage_is_ignored(wh):
    # 'fired' must NOT broadcast on the stage feed (it runs the execution path instead).
    handler, sent = wh
    res = await handler.handle_stage({"secret": SECRET, "stage": "fired", "symbol": "EURUSD"})
    assert res["status"] == "ignored"
    assert sent == []


async def test_unknown_stage_ignored(wh):
    handler, sent = wh
    res = await handler.handle_stage({"secret": SECRET, "stage": "banana", "symbol": "EURUSD"})
    assert res["status"] == "ignored"
    assert sent == []


async def test_duplicate_stage_is_deduped(wh):
    handler, sent = wh
    payload = {"secret": SECRET, "stage": "sweep", "symbol": "GBPUSD", "session": "NY"}
    r1 = await handler.handle_stage(dict(payload))
    r2 = await handler.handle_stage(dict(payload))
    assert r1["status"] == "ok"
    assert r2["status"] == "deduped"
    assert len(sent) == 1               # only ONE message despite two identical alerts


async def test_armed_and_invalidated_render(wh):
    handler, sent = wh
    await handler.handle_stage({"secret": SECRET, "stage": "armed", "symbol": "XAUUSD"})
    await handler.handle_stage({"secret": SECRET, "stage": "invalidated",
                                "symbol": "USDJPY", "detail": "session end"})
    texts = [s["text"] for s in sent]
    assert any("🔔" in t and "XAUUSD" in t for t in texts)
    assert any("❌" in t and "USDJPY" in t for t in texts)
