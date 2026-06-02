# WiseMind Split Indicator Playbook

## Wise London v1.0 + Wise NY v1.0

**Origin:** Split from Wise Indicator v9.25 (3,703-line monolith) into two session-specific scripts.
**Compiled:** Both 0 errors in TradingView Pine v6.
**London:** 2,667 lines | **NY:** 2,447 lines

---

## Why Two Scripts?

1. **Token limit solved** — the monolith hit TradingView's 100,256 compiled-token ceiling (CE10295). Each half is well under the cap.
2. **Faster load** — each chart only computes the session you're trading, not both.
3. **Independent tuning** — you can adjust London settings without affecting NY, and vice versa.
4. **Cleaner alerts** — London alerts say `WMFx LDN`, NY alerts say `WMFx NY`. No ambiguity in Telegram.

---

## How to Run Both

| Setup | Chart 1 | Chart 2 |
|-------|---------|---------|
| Symbols | EURUSD (or XAUUSD) | Same symbol |
| Indicator | **Wise London v1.0** | **Wise NY v1.0** |
| Timeframe | 1m (for 1m precision fire) or 5m/15m | Same |
| Session to trade | London 03:00–05:15 CET | NY 08:30–11:00 CET |

Both auto-detect the symbol profile (EUR/XAU/Custom). You don't need to configure profile manually unless your broker uses unusual ticker names.

---

# PART 1 — WISE LONDON v1.0

## What It Does

Fires T1 and T2 signals during the **London killzone** (default 03:00–05:15 exchange time). Watches Asia H/L as the primary sweep target. Contains the full manipulation protection state machine for London entries.

## Sessions Tracked

| Session | Default Window | Purpose |
|---------|---------------|---------|
| Asia | 20:00–00:00 | Builds the range. Sweep targets = Asia High + Asia Low |
| London | 03:00–05:15 | **Active trading window.** All signals fire here |

> London script does NOT track NY. No NY session box, no NY signals.

## Signal Types

### T1 — Immediate Reversal at Sweep

**Logic:** Asia H/L gets swept during London → price immediately reverses → strong engulfing candle fires at the sweep level.

**Manipulation protection modes:**
- **1st Entry Only** — aggressive, fires on first qualifying engulf after sweep
- **2nd Entry Only** — waits for a manipulation wick (stop-hunt), then fires on the second clean engulf
- **Both** — fires whichever comes first
- **Auto** (default) — if Asia range > threshold (1.5× ATR), uses 2nd entry (safer in volatile conditions). Otherwise uses 1st entry.

**Filters applied to T1:**
- Engulf body must be ≥ 90% of candle range (default)
- Formal engulfing pattern required (close engulfs previous body)
- Volume confirmation: engulf candle volume > 1.5× 20-bar average
- Low-volume filter: min candle range 0.4× ATR, min avg body 0.3× ATR, min vol ratio 0.7×
- PD touch within 15 bars of sweep
- Setup lifespan: active for entire London window (+buffer bars)
- Max distance from swept level: 1.0× ATR
- Bias filter (if enabled): only longs in bullish bias, only shorts in bearish
- Session signal limit: max 1 signal per session (configurable)
- Asia range filter: blocks if Asia > 12× ATR or > 500 ticks (EUR) / 4000 ticks (XAU)
- Block if no sweep yet
- Block if opposite Asia side already swept (e.g., AH swept → blocks T1 SHORT)
- Consolidation filter (ATR5/ATR50 < 0.6)
- HTF alignment (off by default; can block counter-trend)
- FVG gate (optional: require FVG nearby)

### T2 — AMD Retracement (Sweep → Displace → Retrace → Engulf)

**Logic:** Asia H/L gets swept → price displaces away from sweep by ≥ 1.25× ATR (EUR) or 1.50× ATR (XAU) → price retraces back into the Asia range (PD zone) → strong engulfing candle fires.

**T2-specific parameters:**
- Displacement threshold: 1.25× ATR (EUR), 1.50× ATR (XAU) — boosted for sells (+40%) and Gold (+30%)
- T2 body ratio: 85% (stricter than T1's 90% since T2 has more confirmation)
- Retrace must be inside Asia range (configurable)
- Min RR: 2.5 | Max RR: 4.0
- T2 target zone box visible on chart (yellow, 80% transparent)
- Max 1 T2 per side per session

### 1m Precision Fire

**When:** Chart TF is below Logic TF (e.g., chart = 1m, Logic TF = 15m).

Fires on 1m engulfing candles inside active setups. Two variants:
- **Variant 1 (Synchronized)** — 1m fires only when the Logic TF bar would also fire. Same trades, just earlier price.
- **Variant 2 (Independent)** (default) — fires on any strong 1m engulf inside an active setup. More signals, faster fires.

**1m-specific settings:**
- Body ratio: 80% for both T1 and T2
- SL source: "Use Smart SL Chain" (default) — same chain as Logic TF fires
- Vol confirm mode: Off (legacy v9.18 V2 default)

## SL Chain (London)

Engulf low/high → Swing H/L (16-bar lookback) → London H/L → Asia H/L

Each step checks minimum ATR distance (0.40× for EUR, 0.50× for XAU). If too tight, falls back to next source. SL buffer: 15 ticks added on top.

## TP Engine

Scans candidate levels and picks the best one within min/max RR:

| Level | Default |
|-------|---------|
| Asia H/L | ON |
| PDH/PDL | ON |
| Weak swing (20-bar) | ON |
| Intermediate swing (50-bar) | ON |
| Strong swing (100-bar) | ON |
| 5m FVG | OFF |
| 15m FVG | OFF |
| 30m FVG | OFF |
| Order Blocks | OFF |

Min RR: 2.5 | Max RR: 4.0 | FVG/OB placement: Near side (conservative)

## Edge Filters (v9.25)

Based on 223-chart visual backtest analysis:

| Filter | Default | Impact |
|--------|---------|--------|
| HTF Alignment Mode | Off | When "Block Counter-Trend": suppresses signals against HTF direction. 100% of wins were HTF-aligned. |
| HTF Gate Source | Either agrees | Which HTFs must align: HTF1 only, HTF2 only, Both, Either |
| Block sells if HTFs Bullish | OFF | Blocks ALL shorts when HTFs bullish |
| Block buys if HTFs Bearish | OFF | Blocks ALL longs when HTFs bearish |
| Sell Displacement Boost | 1.4× | Shorts need 40% more displacement. Sells had weaker displacement in losses. |
| Gold Displacement Boost | 1.3× | Gold needs 30% more displacement than EUR. Applied to all Gold entries. |
| Consolidation Mode | Warn | Off/Warn/Block. 99% of wins were NOT in consolidation. |
| Consolidation Threshold | 0.6 | ATR5/ATR50 below this = consolidation detected |
| FVG Badge | ON | Shows ✦ when FVG is nearby. 90% of wins had FVG. |
| Require FVG (strict) | OFF | Only fires when FVG within 2× ATR. Removes ~10% of wins. |
| Show signal grade | ON | A+ (4/4), A (3/4), B (2/4), C (1 or less) |

**Signal Grade Calculation:**
Score starts at 0, adds 1 for each:
1. Strong displacement (engulf body > 0.9× candle range)
2. FVG nearby (within 2× ATR)
3. HTF aligned (both TF1+TF2 agree)
4. NOT in consolidation

Grade: **A+** = 4/4 | **A** = 3/4 | **B** = 2/4 | **C** = 0-1

## London Inputs (complete list)

| Group | Input | Default |
|-------|-------|---------|
| **Symbol Auto-Profile** | Auto-detect | ON |
| | Override profile | Auto |
| **Logic TF** | Logic Timeframe | 15m |
| | Enable 1m Fire | ON |
| | 1m Fire Variant | Variant 2 — Independent |
| | 1m Body % T1 | 0.80 |
| | 1m Body % T2 | 0.80 |
| | 1m SL Source | Smart SL Chain |
| | 1m Vol Confirm | Off (legacy) |
| **Sessions** | Asia | 2000-0000 |
| | London | 0300-0515 |
| | Extend signals N bars | 0 |
| **T1 Rules** | Enable T1 | ON |
| | Max 1 T1 per side | ON |
| | Block T1 if opposite swept | ON |
| **T2 Rules** | Enable T2 | ON |
| | Max 1 T2 per side | ON |
| | T2 Body % | 0.85 |
| | T2 Displacement (× ATR) | 1.25 (EUR) / 1.50 (XAU) |
| | Retrace inside Asia | ON |
| | T2 Min RR | 2.5 |
| | T2 Max RR | 4.0 |
| **Bias Filter** | Apply bias filter | ON |
| **Manipulation** | Entry Mode | Auto |
| | Asia vol threshold | 1.5× ATR |
| | Manip wick size | 0.10 (EUR) / 0.15 (XAU) |
| **Sweep** | Asia H/L | ON |
| | PDH/PDL | ON |
| | PWH/PWL | ON |
| | Lookback | 50 bars |
| | Close back required | ON |
| **PD Touch** | Window | 15 bars |
| | Max zones | 5 |
| **Engulfing** | Min Body % | 0.90 |
| | Require formal engulf | ON |
| **Low-Vol Filter** | Enable | ON |
| | Min candle range | 0.4× ATR |
| | Min avg body | 0.3× ATR |
| | Min vol ratio | 0.7× |
| **Vol Confirm** | Require spike | ON |
| | Override mult | ON |
| | Multiplier | 1.5× |
| **Setup Lifespan** | Full London window | ON |
| | Max distance | 1.0× ATR |
| **Signal Limits** | Max per session | 1 |
| **Asia Range** | Max range (× ATR) | 1.5 |
| | Block if huge | ON |
| | Huge threshold | 12.0× ATR |
| | Block if > N ticks | ON |
| | Max ticks | 500 (EUR) / 4000 (XAU) |
| **TP Engine** | Min RR | 2.5 |
| | Max RR | 4.0 |
| | TP buffer | 0 ticks |
| **HTF Alignment** | Mode | Off |
| | Score threshold | 25 |
| **Manual Bias** | Your Bias | Auto |
| **HTF Trend TFs** | TF1 | 15m |
| | TF2 | 1H |
| | Lookback | 50 |
| **Trade Visuals** | SL Buffer | 15 ticks |
| | SL Swing Lookback | 16 bars |
| | SL Min ATR Dist | 0.40 (EUR) / 0.50 (XAU) |
| | Engulf first | ON |
| | Show SL source | ON |
| | Show SL/TP boxes | ON |
| **Outcome Tracking** | Auto BE | ON |
| | BE Trigger | 1.5 R |
| **Alerts** | Enable phone alerts | ON |
| | Alert on 5m fires | ON |
| | Alert on 1m fires | ON |
| | Play chart sound | ON |

## London Alert Messages

- `WMFx LDN — T1 LONG 🟢 [EUR] [5m] ...`
- `WMFx LDN — T2 SHORT 🔴 [XAU] {1m-V2} ...`
- JSON webhook with `"session": "London"` for bot integration

---

# PART 2 — WISE NY v1.0

## What It Does

Fires T1 and T2 signals during the **NY killzone** (default 08:30–11:00 exchange time). Watches **London H/L as primary sweep targets** (Model A) with Asia H/L as fallback. Contains the NY-specific manipulation protection and Smart SL Chain.

## Sessions Tracked

| Session | Default Window | Purpose |
|---------|---------------|---------|
| Asia | 20:00–00:00 | Builds the range. Fallback sweep targets if London didn't sweep them |
| London | 03:00–05:15 | **Tracked for H/L only** — no signals fire. London H/L = primary NY sweep targets |
| NY | 08:30–11:00 | **Active trading window.** All signals fire here |

> NY script tracks London price action to compute London High/Low, but does NOT fire any London signals. London box is drawn for visual reference.

## NY Sweep Model

**Model A + Asia Fallback** (default):
1. **Primary:** London High and London Low are always watched as sweep targets
2. **Fallback:** If Asia H/L was NOT swept during London, NY also watches those levels
3. **Pure Model A:** London H/L only (no Asia fallback)

**Per-source sweep toggles:**
- NY accepts Asia High sweep: ON
- NY accepts Asia Low sweep: ON
- NY accepts London High sweep: ON
- NY accepts London Low sweep: ON

**London-swept-today gate:** NY tracks whether London H or L has been swept by price at any point. The `sweptLH` / `sweptLL` flags persist for the day.

## Signal Types

### NY T1 — Immediate Reversal at Sweep

Same core logic as London T1 but applied to London H/L (or Asia H/L fallback) sweep during the NY session.

**NY T1 body ratio:** 0.85 (slightly stricter than London's 0.90 for T1 — NY has more noise).

**NY manipulation protection:** Same 4 modes (1st/2nd/Both/Auto) with NY-specific wick threshold (0.20× ATR manual, profile-overridden).

### NY T2 — AMD Retracement

Same AMD state machine: sweep → displace → retrace → engulf. Applied to NY session sweeps.

**NY T2 body ratio:** 0.85
**Retrace must be inside reference range:** ON (same concept as London's "retrace inside Asia" but applied to whatever NY swept — London or Asia range)

### NY 1m Precision Fire

Same variants (V1 Synchronized, V2 Independent) applied to NY setups. Fires on 1m engulfs inside active NY setups.

## NY Smart SL Chain

More fallback steps than London because NY has more reference levels:

**Engulf low/high → Swing H/L → NY session H/L → London H/L → Asia H/L**

Each step checks min ATR distance. Falls back to next source if too tight. SL buffer: 15 ticks.

## NY-Specific Blocking Rules

| Rule | Default | Why |
|------|---------|-----|
| Block NY if London range > N ticks | ON | If London already moved huge, daily volatility is "spent" — NY tends to be choppy |
| Max London ticks before block | 500 (EUR) / 4000 (XAU) | Tick-based hard cap |
| Max NY signals per session | 1 | First T1 or T2 fire wins, then NY locks |
| Asia range blocks | Same as London | Huge Asia = blocks everything |

## Edge Filters — NY-Specific

All the same v9.25 edge filters as London, plus:

| Filter | Default | Impact |
|--------|---------|--------|
| NY Sell HTF Gate | Off | "Block if HTF Bullish" or "Require HTF Bearish". 73% of NY losses lacked HTF alignment. |
| NY Sell: extra min RR | 0.0 (off) | Raises the minimum RR floor for NY shorts only. Set to 3.0+ to require higher-conviction shorts. |
| LOW EDGE badge | ON | Shows warning when edge score is low |

## NY Inputs (complete list)

Everything London has **except London T1 rules and London manipulation state machine**, plus:

| Group | Input | Default |
|-------|-------|---------|
| **NY Engine** | Enable NY engine | ON |
| | NY sweep targets | Model A + Asia fallback |
| | Max NY signals | 1 |
| | Block if London huge | ON |
| | Max London ticks | 500 (EUR) / 4000 (XAU) |
| | NY T1 Body % | 0.85 |
| | NY T2 Body % | 0.85 |
| | NY Entry Mode (T1) | Auto |
| | NY Manip wick | 0.20 (manual) / profile-overridden |
| | NY Auto vol threshold | 1.5× ATR |
| | NY accepts AH/AL/LH/LL | All ON |
| | Show NY entry labels | ON |
| | Show manipulation boxes | ON |
| **Sweep** | Sweep London H/L | ON (NY-only input) |
| **Edge (NY-specific)** | NY Sell HTF Gate | Off |
| | NY Sell extra min RR | 0.0 |
| | Show LOW EDGE badge | ON |

## NY Alert Messages

- `WMFx NY — T1 LONG 🟢 [EUR] [5m] ...`
- `WMFx NY — T2 SHORT 🔴 [XAU] {1m-V2} ...`
- JSON webhook with `"session": "NY"` for bot integration

---

# PART 3 — SIDE-BY-SIDE COMPARISON

## What's in London ONLY (removed from NY)

| Feature | Notes |
|---------|-------|
| London T1 fire engine | Full T1 state machine with manipulation protection |
| London T2 AMD engine | Full AMD retracement state machine |
| London manipulation state machine | States 0→1→2→3 (idle→1st engulf→manip armed→fired) |
| London signal counters | `londonLongCount`, `londonShortCount` |
| London 1m precision fire | 1m engulfs inside London setups |
| `sessionBufferBars` input | Extend signals past London close |
| `gT1` input group | T1-specific enable, max 1 per side, block if opposite swept |
| London-specific `gLimits` | Max signals per London session |
| `blockIfNoSweep` | Block if no sweep yet (London-only gate) |

## What's in NY ONLY (removed from London)

| Feature | Notes |
|---------|-------|
| NY T1 fire engine | With London H/L sweep evaluation + Model A logic |
| NY T2 AMD engine | AMD applied to NY session sweeps |
| NY manipulation protection | NY-specific wick threshold and state |
| NY signal counter | `nySignalCount` |
| NY 1m precision fire | 1m engulfs inside NY setups |
| NY Smart SL Chain | 5-step: engulf→swing→NY→London→Asia |
| London H/L tracking | Computes London High/Low from price (for sweep targets) |
| London H/L sweep detection | `sweepLondon` toggle, `sweptLH`/`sweptLL` flags |
| `gNY` input group | All NY-specific settings |
| `sweepLondon` toggle | Sweep London H/L (not in London script) |
| `edgeNySellGate` | NY Sell HTF Gate |
| `edgeNySellMinRR` | NY Sell extra min RR |
| `blockNyIfLondonHuge` | Block NY if London ranged too wide |
| `maxNyTicks` | London tick cap before NY block |
| NY session box | Visual box for NY session |

## What's SHARED (identical in both)

| Feature | Notes |
|---------|-------|
| Symbol Auto-Profile | EUR/XAU/Custom auto-detect |
| Logic TF system | All logic on configurable TF (default 15m) |
| 1m Precision Fire framework | Same variant system, same body/vol settings |
| Asia session tracking | Asia box, Asia H/L, Asia range filter |
| FVG detection | 5m/15m/30m multi-TF FVGs |
| Order Blocks | OB detection and display |
| Sweep detection | Asia H/L sweep (shared), PDH/PDL, PWH/PWL |
| PD Touch | Same window and zone logic |
| Engulfing filter | Same body ratio, formal engulf requirement |
| Low-volume filter | Same thresholds |
| Volume confirmation | Same multiplier system |
| TP Engine | Same levels, same min/max RR, same placement |
| Swing H/L structure | Weak/Int/Strong swings |
| HTF Alignment | Legacy mode + v9.25 edge gates |
| Bias filter matrix | Bullish/Bearish/Neutral/Auto |
| Edge filters | Displacement boosts, consolidation, FVG badge, grade |
| Trade outcome tracking | Win/loss/BE tracking, auto BE move |
| Dashboard | Session status, bias, grade (different theme per script) |
| Watch panel | Live setup status (different color per script) |
| Phone alerts | Rich push with entry/SL/TP/RR |
| JSON webhook | Full signal payload for bot |
| Monthly stats | Win/loss/BE per-month table |
| PDH/PDL/PWH/PWL | Daily/weekly liquidity lines |

---

# PART 4 — DASHBOARD & VISUAL DIFFERENCES

| Element | London | NY |
|---------|--------|-----|
| Dashboard title | "Wise London v1" | "Wise NY v1" |
| Dashboard theme | Blue (#2962ff) | Orange (#ff6f00) |
| Watch panel title | "LDN WATCH" | "NY WATCH" |
| Watch panel border | Blue | Orange |
| Entry label tag | [LDN] | [NY] |
| Alert prefix | WMFx LDN | WMFx NY |
| Webhook session | "London" | "NY" |
| Session boxes shown | Asia + London | Asia + London + NY |

---

# PART 5 — WEBHOOK JSON FORMAT

Both scripts send identical JSON structure to the bot. The `session` field tells the bot which script fired:

```json
{
    "secret": "wisemind2026",
    "version": "1.0",
    "symbol": "EURUSD",
    "side": "LONG",
    "trade": "T1 LONG (1st)",
    "session": "London",          // or "NY"
    "profile": "EUR",
    "entry": 1.08500,
    "sl": 1.08420,
    "sl_source": "engulf",
    "tp": 1.08750,
    "tp_source": "PDH",
    "rr": 3.1,
    "swept": "AL",
    "after_manipulation": false,
    "asia_wide": false,
    "tf": "15m",
    "tf_type": "15m",
    "displacement_atr": 1.85,
    "engulf_body_pct": 0.92,
    "vol_spike": 1.34,
    "htf_aligned": true,
    "signal_grade": "A+",
    "fvg_nearby": true,
    "consolidation": false,
    "conflict_resolved": false
}
```

The bot's `signal_utils.py` handles both sessions identically — it reads `signal_grade` first (v9.25 path), falls back to `quality_score` (v9.22 path), then Python scoring.

---

# PART 6 — SETUP CHECKLIST

## Before London Session (03:00 CET)

1. Open Chart 1 with **Wise London v1.0** on EURUSD (or XAUUSD) at 1m or 5m
2. Check dashboard: Asia range should be < 1.5× ATR (green = good, amber = caution, red = blocked)
3. Asia box should be visible with clear High and Low levels
4. Bias filter should show your directional bias or "AUTO"
5. Wait for Asia H/L sweep during London killzone
6. Signal fires → check grade (A+ or A preferred) → execute

## Before NY Session (08:30 CET)

1. Open Chart 2 with **Wise NY v1.0** on same symbol at 1m or 5m
2. Check dashboard: London range should be < max ticks (not blocked)
3. London H and L lines should be visible as sweep targets
4. NY engine should show "ACTIVE" in dashboard
5. Wait for London H/L sweep (or Asia H/L fallback) during NY killzone
6. Signal fires → check grade → check for NY-specific warnings → execute

## Both Sessions

- **Grade A+ or A** → full size position (1% risk)
- **Grade B** → reduced size or skip depending on other confluence
- **Grade C** → skip the trade
- **CONSOL badge** → extra caution, likely skip
- **Counter-trend without HTF alignment** → skip unless you have strong conviction
- **After BE move** → trade is free, let it run to TP

---

# PART 7 — RECOMMENDED SETTINGS

These are already baked in as defaults. Only change if you have a specific reason:

| Setting | Value | Why |
|---------|-------|-----|
| Logic TF | 15m | Structure on 15m, entry on 1m. Best balance of signal quality and precision. |
| 1m Fire Variant | V2 Independent | More signals, catches fast moves. V1 is conservative. |
| Min Body % (T1) | 0.90 | Strict — ensures strong conviction candles only |
| T2 Body % | 0.85 | Slightly looser for T2 since it has displacement confirmation |
| Vol Confirm | 1.5× | Ensures volume backs the move |
| Min RR | 2.5 | Below this the reward doesn't justify the risk |
| Max RR | 4.0 | Caps greed — levels beyond 4R are low-probability |
| SL: Engulf first | ON | Tightest correct invalidation = best RR |
| Edge: Consolidation | Warn | Alerts you but doesn't block (you decide) |
| Edge: HTF Gate | Off | Turn ON once you're comfortable reading HTF bias |
| Auto BE at 1.5R | ON | Protects profits, eliminates losers-after-winners |

---

*Generated from Wise Indicator v9.25 split — May 2026*
*Files: `wise_london_v1.pine` (2,667 lines) | `wise_ny_v1.pine` (2,447 lines)*
