"""
Tool agency (read-only) — lets Claude actually LOOK at the account/stats to answer
questions like "how am I doing today?" or "what's open?".

SAFETY: only READ-ONLY tools here. Write actions (close, pause) are NOT given to the
agent — they stay as explicit admin-gated Telegram commands so every action requires
Michael's approval (his command IS the approval).
"""

import json
import logging

logger = logging.getLogger(__name__)

# Anthropic tool schemas (read-only)
TOOLS = [
    {
        "name": "get_open_positions",
        "description": "Get the trader's currently open MT5 positions (symbol, side, volume, SL, TP, floating profit).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_account",
        "description": "Get the trading account balance, equity, currency and server.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_stats",
        "description": "Get performance stats: win rate, expectancy (R/trade), total R, breakdown by session and symbol, recent streak.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


async def _execute_tool(name: str, _input: dict) -> dict:
    import mt5_executor
    import stats as _stats
    try:
        if name == "get_open_positions":
            return {"positions": await mt5_executor.get_open_positions()}
        if name == "get_account":
            return await mt5_executor.get_account_info()
        if name == "get_stats":
            return await _stats.compute_stats()
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)[:150]}


async def run_agent(claude, model: str, system_prompt: str, question: str, max_rounds: int = 4) -> str:
    """Run a read-only tool-use loop and return Claude's final text answer."""
    messages = [{"role": "user", "content": question}]
    for _ in range(max_rounds):
        resp = await claude.messages.create(
            model=model, max_tokens=900, system=system_prompt,
            tools=TOOLS, messages=messages,
        )
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", "") == "tool_use":
                    out = await _execute_tool(block.name, block.input or {})
                    logger.info(f"agent tool: {block.name}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str),
                    })
            messages.append({"role": "user", "content": results})
        else:
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return "I gathered the data but couldn't finish the analysis — try asking again."
