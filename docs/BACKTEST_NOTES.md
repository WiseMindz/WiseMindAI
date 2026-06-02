# 📊 BACKTEST & BEHAVIORAL EVIDENCE — the "why" behind every filter

This is the evidence ledger for the indicator logic. When you (Claude or Cursor) propose a filter change,
**cite the finding here** so we never re-argue a decision from memory. Referenced by `docs/HANDOFF.md` §5.

> ⚠️ This used to live only in `/tmp/london_backtest_analysis.txt` — which gets wiped. It's now
> permanent in the repo so Cursor has the full context.

---

## A. EURUSD LONDON SESSION BACKTEST — June–Oct 2025

**Dataset:** 110 trading days | 71 traded | 39 no-trade days
**Results:** 40 WINS (56.3%) | 27 LOSSES (38.0%) | 4 BE (5.6%)

### Key findings — what separates wins from losses
1. **Grade (strongest signal).** 100% of wins (40/40) were "Good Trade"; only 81% of losses (22/27).
   5 losses were self-identified "Bad Trade" (counter-trend, both-sides-swept, missing confirmations) =
   ~19% of all losses → the easy-to-filter ones.
2. **Both sides swept (strong loss predictor).** Wins with AH+AL both swept: 3/40 (8%); losses: 5/27
   (19%). When both Asia sides are swept, direction is confused → 2.4× more likely in losses.
3. **FVG confluence (strong win predictor).** Wins with FVG: 19/40 (48%); losses: 9/27 (33%). FVG present
   = 1.5× more likely a win.
4. **Asia-range retrace = 100% win rate** in this dataset. Wins with retrace inside Asia: 4/40; losses: 0.
   When the retrace goes back INSIDE the Asia range it was a perfect T2.
5. **Forced 2nd entry correlates with losses.** 2nd-entry in wins: 5/40 (12%); in losses: 9/27 (33%). The
   best wins fire clean on the 1st. Don't force the 2nd entry.
6. **Counter-trend = the 5 "Bad Trade" losses** (e.g. "uptrend but took a short", "sweep into BSL then
   reversed", "strong uptrend with reaction on OB30"). HTF alignment would block these.
7. **Sweep-target bias.** AH swept → 52% of losses vs 35% of wins. AL swept → 40% of wins vs 33% of
   losses. **Shorting after an AH sweep has worse odds than longing after an AL sweep.**
8. **Deep retrace before entry = worse.** Retrace/pullback in wins 35%, losses 48%. Best entries are AT
   the sweep level, not deep pullbacks.
9. **HTF OB as the entry zone correlates with losses** (8% wins vs 19% losses) — a 15m/30m OB gives false
   security; the 5m FVG at the sweep level is more reliable.

### Loss anatomy (patterns)
- A) Sweep + immediate engulf, no pullback to FVG (9 losses) — aggressive, no zone support.
- B) Both sides swept → confused direction (5).
- C) Counter-trend vs strong opposite momentum (5).
- D) Late entry near session close — not enough time to TP (3).
- E) SL too tight (engulf-wick clipped by volatility) (5).

### Projected win-rate impact (conservative, overlaps exist)
- Both-sides-swept block: −5L, −3W → 62.7%
- HTF gate: −5L → 62.7%
- Combined 1+2: −10L, −3W → **~65–70% WR** with tighter selection.

### → Drove these London changes / queue items
- **Shipped:** both-sides-swept gate, HTF gate mode, sell displacement boost (1.4×), FVG badge/require,
  grade system, SL min-distance (tight-SL losses).
- **Queued (HANDOFF §5):** `londonSellGate` (finding #7), `minBarsBeforeSessionEnd` (loss D),
  grade-penalty system (#1/#2/#6), prefer-clean-1st-entry (#5).

---

## B. XAU/USD (GOLD) NY SESSION — behavioral spec (~30 documented trades)

Michael documented ~30 gold NY trades with annotations + chart screenshots. These are the behavioral
spec the **NY v2.0 Gold/PO3 update** was built from (see HANDOFF §3).

### Recurring winning patterns
- **"Sweep of Previous NY highs then PO3 formation → continuation with NY"** ← the #1 pattern.
- "Sweep PRV NY Highs then London highs → into 15m FVG → rejected + engulfed 5m" (TP 2.76%).
- "Dropped into 15m OB → reacted + rejected, higher lows → down to 1m → 1m FVG + pullback → entry on 1m
  engulf."
- "Reacted on 15m FVG + rejected → 5m engulf → SL below NY Lows + TP on NY Highs."
- "Swept NY Lows early, ranged higher, London swept AH, dropped into **30m FVG inside Asia range** →
  reacted + rejected → 1m engulf → TP on NY Highs."
- "PO3 — Asia A → London M → NY D — TP SSL 2.65%."
- Many "Double Confirmation" 1m entries; TPs on London/NY/Asia H/L and SSL/BSL; RR 2.65–5.23.

### NO-TRADE conditions observed
- "Price already ranged" / "ranged quickly" (consolidation — `edgeConsolidationMode`).
- "NEWS Release."

### → Drove these NY v2.0 changes (all shipped, see HANDOFF §3)
1. **Prev-NY High/Low (PNYH/PNYL) sweep targets** — the engine literally couldn't arm on these before.
2. **15m + 30m FVG as PD-touch retrace zones** — gold retraces into HTF zones that the old 5m-only gate
   ignored (the single biggest gold fix).
3. **PO3 badge** — context that manipulation (London/Prev-NY) was swept before NY distribution.
4. **XAU profile tune** — manip wick 0.18, SL min 0.60, vol confirm 1.15 (gold ranges + noisy volume).

### → Open / queued
- **EURUSD NY backtest screenshots incoming** (HANDOFF §5 item 1) — validate PNYH/PNYL + 15m/30m zones on
  EURUSD and fine-tune.
- **Gold RR cap** — gold hit 5.23R but `maxRR`/`t2MaxRR` cap at 4.0 (HANDOFF §5 item 5).

---

## C. How to use this file
- Before changing a filter, find the finding here. If there's no evidence, say so and propose how to get
  it (more backtest screenshots) rather than guessing.
- When a new backtest is run (e.g. the EURUSD NY set), **append a new section** with dataset size, W/L/BE,
  and the findings — same format as §A. Then update `docs/HANDOFF.md` §5.
