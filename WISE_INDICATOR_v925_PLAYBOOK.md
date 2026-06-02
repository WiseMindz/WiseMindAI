# Wise Indicator v9.25 — Complete Playbook

> Built from 223 real chart analyses across EURUSD (London + NY) and XAUUSD (NY).
> Every setting, what it does, when to change it, and the recommended values.

---

## TABLE OF CONTENTS

1. [Quick Start — The 5-Minute Setup](#1-quick-start)
2. [How the Indicator Works (Big Picture)](#2-how-it-works)
3. [Settings Groups — Full Breakdown](#3-settings)
4. [The Dashboard — What Every Row Means](#4-dashboard)
5. [The Live Watch Panel](#5-live-watch)
6. [Entry Labels — Reading Them](#6-entry-labels)
7. [Edge Filters v9.25 — The 223-Chart Proof](#7-edge-filters)
8. [Signal Grading System (A+/A/B/C)](#8-grading)
9. [Trade Outcome Tracking](#9-outcome-tracking)
10. [Recommended Settings by Profile](#10-recommended)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. QUICK START — The 5-Minute Setup <a name="1-quick-start"></a>

### Step 1: Add to chart
Open Pine Editor → paste the script → Add to Chart on EURUSD or XAUUSD, 5m timeframe.

### Step 2: Verify auto-profile
The dashboard (top right) should show `EUR ⚙ AUTO` or `XAU ⚙ AUTO`. If your broker uses a non-standard name (like `GOLD/USD` or `EURUSDx`), go to Settings → Symbol Auto-Profile → Override profile → Force EURUSD or Force XAUUSD.

### Step 3: Set Logic Timeframe
**Settings → Multi-Timeframe Logic → Logic Timeframe = 5**
This is critical. The entire strategy was calibrated on 5m structure. If you set it to 15, the indicator calculates on 15m bars and everything changes.

### Step 4: Verify Edge Filters are ON
Settings → Edge Filters (v9.25):
- HTF Alignment Mode = **Block Counter-Trend** ✓
- HTF Gate Source = **Both must agree** ✓
- NY Sell HTF Gate = **Block if HTF Bullish** ✓

### Step 5: Set alerts
Create a TradingView alert:
- Condition: Wise Indicator v9.25 → "Any alert() function call"
- Actions: Push notification + Webhook URL (if using the Telegram bot)

### You're ready. Only trade A+ and A grades.

---

## 2. HOW THE INDICATOR WORKS (Big Picture) <a name="2-how-it-works"></a>

The indicator runs a **session-based ICT strategy** in two killzones:

```
ASIA SESSION (20:00-00:00 exchange time)
  → Establishes the range (Asia High / Asia Low)
  → This is the liquidity pool that London/NY will hunt

LONDON KILLZONE (03:00-05:15 exchange time)  
  → Watches for price to SWEEP Asia H/L (grab liquidity)
  → After sweep: looks for strong engulfing candle = ENTRY
  → Two trade types: T1 (immediate reversal) and T2 (AMD retracement)

NY KILLZONE (08:30-11:00 exchange time)
  → Watches for sweeps of London H/L and/or remaining Asia H/L
  → Same T1/T2 logic, separate signal counter
  → Requires London to have swept first (NY gate)
```

### The Two Trade Types

**T1 — Immediate Reversal at Sweep**
1. Price sweeps Asia/London level (liquidity grab)
2. Strong engulfing candle forms immediately at the sweep
3. Entry on the engulfing candle close
4. SL below/above the engulf wick → TP at opposing liquidity

**T2 — AMD (Accumulation → Manipulation → Distribution)**
1. Price sweeps Asia/London level (manipulation)
2. Price displaces AWAY from sweep by ≥1.25× ATR (distribution)
3. Price retraces BACK into Asia range (discount/premium zone)
4. Strong engulfing candle at the retrace = entry
5. Higher RR because entry is deeper in the range

### Signal Flow
```
Sweep detected → Engulf quality check → Volume check → Session limit check
→ HTF alignment gate → Edge filters (displacement/FVG/consolidation)
→ FIRE signal → Entry label + Alert + Webhook JSON
→ Outcome tracking (TP/SL/BE monitoring)
```

---

## 3. SETTINGS GROUPS — Full Breakdown <a name="3-settings"></a>

### ◆ Symbol Auto-Profile (v9.14)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Auto-detect symbol profile** | Reads ticker name, applies EUR or XAU presets automatically | **ON** |
| **Override profile** | Force a specific profile if auto-detect fails | **Auto** (change only if broker has weird naming) |

**What the profile controls:** Asia tick caps, manipulation wick sizes, SL minimums, volume thresholds, T2 displacement requirements. EURUSD and XAUUSD have very different volatility characteristics — the profile auto-tunes for each.

**Profile preset values:**

| Parameter | EURUSD | XAUUSD | Custom |
|-----------|--------|--------|--------|
| Max Asia Ticks | 500 | 4000 | Manual |
| Manip Wick (×ATR) | 0.10 | 0.15 | Manual |
| SL Min (×ATR) | 0.40 | 0.50 | Manual |
| Vol Confirm (×avg) | 1.20 | 1.20 | Manual |
| T2 Displacement (×ATR) | 1.25 | 1.50 | Manual |

---

### ◆ Multi-Timeframe Logic (v9.7)

This is the **most important setting group** for signal quality.

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Logic Timeframe** | ALL strategy math (sweeps, engulfs, volume) runs on this TF regardless of chart TF | **5** |
| **Enable 1m Precision Fire** | When chart is 1m and logic TF is 5m: fires on 1m engulfing candles inside active 5m setups. Gets you in earlier with tighter SL. | **ON** |
| **1m Fire Variant** | V1 = only fires when 5m would also fire (conservative). V2 = fires on any strong 1m engulf in active setup (more signals, faster). | **Variant 2** |
| **1m Min Engulf Body % (T1)** | Body quality required for 1m candle to fire T1 | **0.85** |
| **1m Min Engulf Body % (T2)** | Body quality required for 1m candle to fire T2 | **0.85** |
| **1m Fire SL Source** | Where 1m fire puts SL. "1m engulf" = tightest (best RR), "5m engulf" = safer, "Smart SL Chain" = full chain | **Smart SL Chain** |
| **1m Vol Confirm Mode** | Volume check on 1m fires. Strict = 1m candle must pass vol. Off = no vol check on 1m (legacy). | **Off** (legacy, avoids filtering valid fast entries) |

**How Logic TF works:**
- Chart TF = 5m, Logic TF = 5m → regular mode, chart bars ARE the logic bars
- Chart TF = 1m, Logic TF = 5m → 1m precision mode: strategy runs on 5m, but 1m engulfs fire trades earlier
- Chart TF = 15m, Logic TF = 5m → signals still computed on 5m data (via request.security), chart is just zoomed out

**CRITICAL: Set Logic TF to 5.** The 223-chart backtest was done on 5m structure. Setting it to 15 changes displacement thresholds, engulf sizing, and sweep timing — all calibration is lost.

---

### ◆ Sessions (Exchange Time)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Asia Session** | Range-building session | **2000-0000** (adjust for your broker's exchange timezone) |
| **London Killzone** | Signal-active window for London | **0300-0515** |
| **NY Killzone** | Signal-active window for NY | **0830-1100** |
| **Extend signals N bars past London close** | Keeps setups alive after London closes. 6 bars × 5m = 30 min. | **0** (default) |

**How to set session times:**
These are in your broker's EXCHANGE time (shown on TradingView's x-axis). If your broker is UTC-5 (e.g., many US brokers), and you trade CET sessions:
- Asia 20:00–00:00 CET = 2000-0000 exchange time
- London 09:00–11:15 CET = 0300-0515 exchange time
- NY 14:30–17:00 CET = 0830-1100 exchange time

Check: when you see the colored session boxes on chart, do they align with when your sessions actually start/end? If not, adjust.

---

### ◆ Session Colors

Toggle visibility and colors for the Asia (purple), London (blue), and NY (gray) session boxes on chart.

---

### ◆ T1 Entry Rules (immediate reversal at sweep)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Enable T1 signals** | Master toggle for all T1 trades | **ON** |
| **Max 1 T1 signal per side per session** | Only 1 T1 LONG and 1 T1 SHORT per London session. Prevents overtrading. | **ON** |
| **Block T1 if opposite Asia side already swept** | If Asia HIGH was already swept → blocks T1 SHORT (market already picked a direction). | **ON** |

---

### ◆ T2 Entry Rules (AMD retracement)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Enable T2 signals** | Master toggle for T2 AMD trades | **ON** |
| **Max 1 T2 per side per session** | Same overtrading protection | **ON** |
| **T2 Min Engulfing Body %** | How clean the engulfing candle must be. 0.80 = 80% body. | **0.80** |
| **T2 min displacement (× ATR)** | After sweep, price must move this far away before retrace is valid. Higher = more confirmation, fewer signals. | **1.25** (EUR), auto **1.50** (XAU) |
| **T2 retrace MUST be inside Asia range** | Purist ICT — entry must be in the discount/premium zone (inside Asia box) | **ON** |
| **T2 Min/Max RR** | RR boundaries for T2 trades | **2.5 min / 4.0 max** |
| **Show T2 zone box** | Draws the yellow box showing where T2 entry zone is | **ON** |

**T2 is the higher-quality trade.** It requires sweep → displacement → retrace → engulf (4-layer confirmation). The 223-chart analysis showed T2 had better consistency than T1.

---

### ◆ Bias Filter Matrix

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Apply bias filter to T1 and T2** | Enables directional filtering based on HTF scores or manual bias | **ON** |

When ON, the Manual HTF Bias setting + HTF Alignment system controls which directions are allowed.

---

### ◆ NY Session Engine (v9.8)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Enable NY engine** | Master toggle for NY session trading | **ON** |
| **NY sweep targets** | What liquidity NY watches. "Model A + Asia fallback" = London H/L primary, Asia H/L fallback. | **Model A + Asia fallback** |
| **Max NY signals per session** | Separate counter from London | **1** |
| **Block NY if London range > N ticks** | If London already moved a lot, NY tends to be choppy | **ON** |
| **Max London ticks before blocking NY** | Hard cap | **500** (EUR) / **4000** (XAU) via profile |
| **T2 NY: retrace in reference range** | Same retrace-in-range rule for NY T2 | **ON** |
| **NY T1/T2 Min Body %** | Same quality standards as London | **0.85 / 0.80** |
| **NY Entry Mode** | 1st/2nd/Both/Auto manipulation protection | **Auto** |
| **NY accepts AH/AL/LH/LL** | Which sweep sources NY uses | **All ON** |

**NY requires London to sweep first.** This is the biggest edge from the backtest: 100% of EURUSD NY wins had London sweep first. The NY engine checks this automatically.

---

### ◆ Manipulation Protection

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Entry Mode** | Controls T1 manipulation protection for London. "2nd Entry Only" = waits for stop-hunt wick before arming. "Auto" = picks based on conditions. | **Auto** (or **2nd Only** for maximum safety) |
| **Auto: Asia range threshold (× ATR)** | When in Auto mode: if Asia was wide (volatile), uses 2nd entry (expects stop hunts). If Asia was tight (clean), uses 1st entry. | **1.5** |
| **Manipulation wick size (× ATR)** | Min wick size to count as manipulation | **0.10** (EUR) / **0.15** (XAU) via profile |
| **Show manipulation boxes** | Orange boxes on chart showing where manipulation was detected | **ON** |

**What "1st" vs "2nd" entry means:**
- **1st entry** = fires immediately on the first engulfing candle after sweep. Aggressive. Good when conditions are clean.
- **2nd entry** = waits for a manipulation wick AFTER the first engulf, then fires on the SECOND engulf. Safer. Filters out fake-outs.
- **Auto** = picks 1st when Asia was narrow (clean conditions), 2nd when Asia was wide (volatile, expect traps).

---

### ◆ Sweep Detection

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Sweep Asia H/L** | Watch for Asia level sweeps | **ON** |
| **Sweep London H/L** | Watch for London level sweeps | **ON** |
| **Sweep PDH/PDL** | Watch for previous day H/L sweeps | **OFF** (optional extra) |
| **Sweep PWH/PWL** | Watch for previous week H/L sweeps | **OFF** |
| **Max bars after Asia to look for sweep** | How long to wait for a sweep | **100** |
| **Sweep must close BACK through level** | The candle must close back through the level, not just wick through | **ON** |
| **Show Sweep Lines** | Draw lines at swept levels | **ON** |

---

### ◆ PD Array Touch

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Must touch within N bars of sweep** | After sweep, price must touch a PD zone within this window | **20** |
| **Max Recent PD Zones to Check** | How many recent FVG/OB zones to check | **4** |

---

### ◆ Strong Engulfing

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Min Body % of Candle Range** | How much of the candle must be body (not wick). 0.85 = 85% body. | **0.85** |
| **Require formal engulfing pattern** | Require candle to formally engulf the previous candle | **OFF** (body % alone is sufficient) |

**From the backtest:** 100% of wins had strong candle bodies (≥80%). 62.5% of Gold losses had weak bodies. This filter is critical.

---

### ◆ Low-Volume / Tiny-Candle Filter

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Enable low-volume filter** | Blocks signals on tiny/low-vol candles | **ON** |
| **Min candle range (× ATR)** | Candle must be at least this big relative to ATR | **0.4** |
| **Min avg body last 5 bars (× ATR)** | Recent price action must show movement | **0.3** |
| **Min volume ratio (× 20-bar avg)** | Current volume must be at least this fraction of average | **0.7** |

---

### ◆ Volume Confirmation

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Require volume spike on engulf** | Engulfing candle must have above-average volume | **ON** |
| **Override vol mult** | Use your own multiplier instead of the profile's | **ON** |
| **× avg** | Volume must be ≥ this × the 20-bar average | **1.0** (set to 1.0 to avoid filtering valid entries with just normal volume) |

---

### ◆ Setup Lifespan

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Setup alive for entire London (+buffer)** | Once sweep happens, the setup stays active for the whole session | **ON** |
| **Max distance from swept level (× ATR)** | How far price can drift from the swept level before setup expires | **1.0** |

---

### ◆ Session Signal Limits

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Max Signals Per Session** | Total T1 + T2 signals in London. 0 = unlimited. | **1** |

This is a prop firm rule: max 1 trade per session. Prevents overtrading.

---

### ◆ Asia Range Filter

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Max Asia Range (× ATR) — warn** | Dashboard shows ⚠ WIDE when exceeded | **1.5** |
| **Block if no sweep yet** | No signals until a sweep happens | **ON** |
| **Block if Asia > huge threshold** | Hard block when Asia is extremely wide | **ON** |
| **Huge Asia threshold (× ATR)** | What counts as "huge" | **10.0** |
| **Block ALL if Asia > N ticks** | Hard tick cap — if Asia is wider than this, session is too volatile | **ON** |
| **Max Asia ticks (hard cap)** | The tick cap | **500** (EUR) / **4000** (XAU) via profile |

---

### ◆ TP Engine — Min/Max RR

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Minimum Risk:Reward** | TP must give at least this RR or signal won't fire | **2.5** |
| **Maximum Risk:Reward (cap)** | Caps RR so TP isn't unrealistically far | **4.0** |
| **TP buffer from level (ticks)** | How far before the TP level to place the actual TP (safety margin) | **2.5** |

---

### ◆ TP Candidate Levels

Toggle which levels the TP engine considers as targets:

| Level | Recommended | Notes |
|-------|-------------|-------|
| 5m FVG | OFF | Too close, gives low RR |
| 15m FVG | OFF | Optional |
| 30m FVG | OFF | Optional |
| Order Blocks | **ON** | Good structural targets |
| Asia H/L | **ON** | Natural liquidity targets |
| PDH/PDL | **ON** | Strong daily levels |
| Weak Swing H/L | **ON** | Most common targets |
| Intermediate Swing H/L | **ON** | Mid-term structure |
| Strong Swing H/L | OFF | Usually too far |

### ◆ TP Placement on FVG/OB zones

| Setting | Options | Recommended |
|---------|---------|-------------|
| **FVG/OB TP placement** | Near side / Middle / Far side | **Near side** (conservative — fills first) |

---

### ◆ Swing H/L Structure

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Weak swing lookback** | Short-term structure | **20** bars |
| **Intermediate swing lookback** | Mid-term | **50** bars |
| **Strong swing lookback** | Long-term | **100** bars |
| **Show lines** | Draw horizontal lines at swing levels | **OFF** (keeps chart clean, used internally for TP) |

---

### ◆ HTF Alignment (Legacy System)

**This is the OLDER HTF system from v9.14.** It works but the v9.25 Edge HTF Gate is more precise.

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **HTF Alignment** | Off / 4H only / 30m only / 30m + 4H must agree / 30m OR 4H | **Off (no filter)** — use the v9.25 Edge HTF gate instead |
| **HTF Score Threshold** | Score needed to count as bullish/bearish (out of 100) | **25** |

**Why keep this OFF:** The v9.25 Edge HTF Gate (below) is more sophisticated — it blocks counter-trend signals specifically, rather than blocking ALL signals when HTF is unclear. Using both creates double-filtering that's hard to reason about.

---

### ◆ Manual HTF Bias

| Setting | Options | Recommended |
|---------|---------|-------------|
| **Your Bias** | Auto / BULLISH / BEARISH / NEUTRAL | **Auto** (lets the HTF scores decide) |

Override this only when you have a strong macro conviction (e.g., NFP day, you know the direction).

---

### ◆ HTF Trend TFs

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **HTF Bias 1** | First timeframe for trend scoring | **30** (30m) |
| **HTF Bias 2** | Second timeframe | **240** (4H) |
| **Trend Lookback** | How many bars to score the trend | **50** |

These feed BOTH the legacy HTF system AND the v9.25 Edge HTF Gate. The scores use volume imbalance (50%), momentum (30%), and structure (20%) to determine bullish/bearish/neutral.

**Dashboard shows:** `30m: BULLISH (29)` means the 30m score is +29 out of ±100. Anything above +25 = bullish. Below -25 = bearish. Between = neutral.

---

### ◆ FVG Display

| Setting | Recommended | Notes |
|---------|-------------|-------|
| Show FVGs | **ON** | |
| Auto-Delete Filled FVGs | **ON** | Keeps chart clean |
| Min FVG Size (ticks) | **4** | Filters noise-level gaps |
| Max Active FVGs per TF | **4** | |
| 5m FVGs | **ON** | Primary entry-timing FVGs |
| 15m FVGs | OFF | Optional |
| 30m FVGs | OFF | Optional for direction |

---

### ◆ Order Blocks

| Setting | Recommended | Notes |
|---------|-------------|-------|
| Show OBs | **OFF** | Adds visual clutter. Used internally for TP. |
| Min Displacement (× ATR) | **1.0** | |
| Max Active OBs | **3** | |

---

### ◆ Trade Visuals

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **SL Buffer (ticks)** | Extra space added below/above SL level | **10** |
| **SL Swing Lookback** | Bars to search for swing H/L for SL placement | **16** |
| **SL Min Distance (× ATR)** | If SL is closer than this, falls back to next-wider source | **0.40** (EUR) / **0.50** (XAU) |
| **SL: Engulf low/high first** | Use the engulfing candle's wick as primary SL (tightest) | **OFF** (Smart SL Chain is safer) |
| **Show SL source in label** | Adds "(engulf)" / "(swing)" / "(London)" / "(Asia)" to label | **ON** |
| **Show SL/TP Boxes** | Green/red boxes from entry to TP/SL | **ON** |

**Smart SL Chain (default):** Tries engulf low → if too tight, tries swing low → if still tight, tries session low → if still tight, uses Asia low. Always picks the tightest valid SL.

---

### ◆ Daily/Weekly Liquidity

| Setting | Recommended | Notes |
|---------|-------------|-------|
| Show H/L from last N days | **1** | Yesterday only |
| Daily High/Low lines | **OFF** | Turn ON when using PDH/PDL as sweep source |
| PWH/PWL lines | **OFF** | |

---

### ◆ Visuals

| Setting | Recommended |
|---------|-------------|
| Entry Labels | **ON** |
| Dashboard | **ON** |
| Live Watch Panel | **ON** |

---

### ◆ Trade Outcome Tracking (v9.23)

| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Auto Move SL to Breakeven** | When price moves X R in your favour, SL moves to entry | **ON** |
| **BE Trigger (R in profit)** | How far price must go before BE kicks in | **1.5** |

This tracks every signal's TP/SL/BE outcome and feeds the monthly stats table (bottom-right corner). When price hits TP = WIN, hits SL = LOSS, hits moved SL at entry = BE.

---

### ◆ Phone Alerts (v9.12)

| Setting | Recommended | Notes |
|---------|-------------|-------|
| Enable rich phone alerts | **ON** | Full trade details in push notification |
| Alert on 5m fires | **ON** | |
| Alert on 1m precision fires | **ON** | |
| Play chart sound on fire | **ON** | Audible when at desk |

**Alert setup in TradingView:**
1. Click "Alert" button (top toolbar)
2. Condition: Wise Indicator v9.25
3. Select: "Any alert() function call"
4. Notifications: Push + Webhook URL
5. Webhook URL: your Railway deployment URL + `/webhook`

---

## 4. THE DASHBOARD — What Every Row Means <a name="4-dashboard"></a>

The dashboard sits at the **top-right** corner of your chart.

| Row | What it shows | What to look for |
|-----|---------------|-----------------|
| **Header** | Profile (EUR/XAU) + session + Logic TF | Should show your correct symbol and "5→15 ⚡" or "5 logic" |
| **Your Bias** | Manual bias override or AUTO | AUTO = indicator decides from HTF |
| **Entry Mode** | 1st only / 2nd only / 1st+2nd | Shows current manipulation protection mode |
| **30m** | 30m trend score: BULLISH/NEUTRAL/BEARISH (+score) | Green = bullish, Gray = neutral, Red = bearish |
| **4H** | 4H trend score | Same color coding |
| **HTF Allows** | What the legacy HTF filter allows | Shows OFF when legacy is disabled (fine if Edge HTF is on) |
| **— Range/Sweep —** | Section header | |
| **Asia Range** | Asia H-L in ticks + status | ✓ OK (green) / ⚠ WIDE (orange) / ⚠⚠ HUGE (red) / ✗ BLOCKED |
| **Long Sweep** | Has Asia Low / London Low been swept? | ✓ AL (green) = swept |
| **Short Sweep** | Has Asia High / London High been swept? | ✓ AH (green) = swept |
| **T1 Status** | Current T1 trade state | Shows FIRED / taken / waiting |
| **T2 Status** | Current T2 trade state | Shows FIRED / taken / waiting |
| **— NY Engine —** | Shows when NY is active | |
| **NY Status** | OK / BLOCKED / LIMIT | Green = can trade, Red = blocked |
| **NY Sweep** | What NY has swept | S:✓ LH = short sweep ready, L:✓ LL = long sweep ready |
| **NY T1/T2 Status** | NY trade states | Same as London rows |
| **Edge v9.25** | Edge filter summary | ✦FVG = FVG nearby, HTF:🟢/🔴/⚪ = HTF direction, A+/A/B/C grade |

---

## 5. THE LIVE WATCH PANEL <a name="5-live-watch"></a>

The Live Watch panel sits at the **top-left** of your chart. It's your real-time trade status:

| Row | What it shows |
|-----|---------------|
| **T1 LONG** | Status of the T1 long setup: "— waiting London" / "watching" / "✓ armed" / "✓ FIRED" |
| **T1 SHORT** | Same for T1 short |
| **T2 LONG** | T2 AMD long status: shows sweep → displacement → retrace → fire stages |
| **T2 SHORT** | Same for T2 short |
| **Asia Range** | Current Asia size with warning |
| **Sweep Mem** | Which levels have been swept today |
| **London Sweep** | London sweep status (swaps to Asia info during NY) |
| **Signals** | Signal count this session (e.g., "1/1" = 1 used out of 1 allowed) |

---

## 6. ENTRY LABELS — Reading Them <a name="6-entry-labels"></a>

When a signal fires, a label appears on the chart. Here's how to read it:

```
▲ LONG T1 [2nd] [NY] [EUR] {1m-V2}
Swept AL → Retrace
SL: 1.16348 (engulf)
TP: 1.16826 @WeakH
RR: 2.58
⚠ ASIA WIDE
✦ FVG
A+
```

**Line by line:**
- `▲ LONG` = direction
- `T1 [2nd]` = trade type + 1st/2nd entry
- `[NY]` = fired during NY session (blank = London)
- `[EUR]` = symbol profile
- `{1m-V2}` = fired on 1m precision, Variant 2 (blank = fired on logic TF)
- `Swept AL → Retrace` = what triggered the trade
- `SL: 1.16348 (engulf)` = stop loss level + which SL source was used
- `TP: 1.16826 @WeakH` = take profit level + which target
- `RR: 2.58` = risk/reward ratio
- `⚠ ASIA WIDE` = warning badge (Asia range was wide)
- `✦ FVG` = FVG proximity badge (high confidence)
- `A+` = signal grade (highest quality)

**SL sources:** `(engulf)` = engulfing candle wick, `(swing)` = swing H/L, `(London)` = London H/L, `(Asia)` = Asia H/L, `(1m engulf)` = 1m candle wick

**TP sources:** `@WeakH/L` = weak swing, `@IntH/L` = intermediate swing, `@AsiaH/L` = Asia level, `@PDH/PDL` = previous day, `@OB` = order block

---

## 7. EDGE FILTERS v9.25 — The 223-Chart Proof <a name="7-edge-filters"></a>

These filters come directly from analyzing 223 real chart screenshots. Every number below is from the data.

### ◆ Edge Filters (v9.25 — 223 charts analyzed)

#### HTF Alignment Mode
**The #1 loss killer.**
- `Block Counter-Trend` (RECOMMENDED) = Blocks signals that go against the selected HTF trend
- `Warn Only` = Shows ⚠ HTF AGAINST badge but still fires
- `Off` = No HTF filtering

**The proof:**
- 100% of EURUSD wins were HTF-aligned
- 72.7% of EURUSD losses had NO HTF alignment
- When HTF alignment missing → 73% chance of loss

#### HTF Gate Source
Controls WHICH timeframes the HTF gate uses:
- `HTF1 only` = 30m only (faster, more responsive)
- `HTF2 only` = 4H only (slower, stronger trend)
- `Both must agree` (RECOMMENDED) = 30m AND 4H must agree. Most selective.
- `Either agrees` = 30m OR 4H can be enough. More permissive.

**How to experiment:** If you find "Both must agree" is too restrictive (blocks too many valid trades), try "Either agrees" first. If still too many losses, the issue isn't the gate — it's the market conditions.

#### NY Sell HTF Gate
- `Block if HTF Bullish` (RECOMMENDED) = No NY shorts when 30m+4H are bullish
- `Require HTF Bearish` = NY shorts ONLY when HTFs actively bearish (strictest)
- `Off` = No NY sell gate

**The proof:** 73% of NY losses lacked HTF alignment. NY shorts against the trend are the #1 loss generator.

#### All Sessions: block sells if HTFs Bullish / block buys if HTFs Bearish
**Global directional gates.** When ON:
- Block sells everywhere (not just NY) when HTFs are bullish
- Block buys everywhere when HTFs are bearish

**Recommended: OFF.** These are nuclear options. Use them only in strong trending markets where you're certain of direction. The counter-trend gate handles most cases.

#### Displacement Quality Boosts
| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Sell Displacement Boost** | Raises the displacement requirement for SHORT signals by this multiplier | **1.2** (20% more required for sells) |
| **Gold Displacement Boost** | Extra multiplier for XAUUSD signals (both directions) | **1.3** (30% more for Gold) |

**The proof:**
- 0% of EURUSD losses had strong displacement
- Gold requires even stronger displacement due to 2-3× higher volatility
- Weak displacement was ONLY present in losing trades

#### Consolidation Mode
| Option | What it does | Recommended |
|--------|-------------|-------------|
| `Off` | Ignores consolidation | |
| `Warn` (RECOMMENDED) | Shows ⚠ CONSOL badge on signals during consolidation | **Warn** |
| `Block` | Completely suppresses signals during consolidation | Use if you want maximum selectivity |

**Consolidation threshold (ATR5/ATR50):** When the 5-bar ATR drops to 60% or less of the 50-bar ATR, the market is consolidating. Default: **0.6**

**The proof:** 50% of Gold losses were in consolidation. 99% of wins were NOT in consolidation.

#### FVG Confirmation
| Setting | What it does | Recommended |
|---------|-------------|-------------|
| **Show ✦ FVG badge** | Shows badge when FVG is within 2×ATR of entry | **ON** |
| **Require FVG for signal (strict)** | Only fires when FVG is nearby. Removes ~10% of valid signals. | **OFF** (use badge as a confidence indicator, not a hard gate) |

**The proof:**
- 85.7% of Gold wins had visible FVG
- 44.1% of EURUSD wins had visible FVG (lower because EURUSD FVGs are subtler)
- FVG nearby = high-confidence setup

#### Signal Quality Badges
| Setting | Recommended |
|---------|-------------|
| Show ⚠ LOW EDGE badge | **ON** |
| Show ⚠ CONSOL badge | **ON** |
| Show signal grade (A+/A/B/C) | **ON** |

---

## 8. SIGNAL GRADING SYSTEM (A+/A/B/C) <a name="8-grading"></a>

Every signal gets a grade based on 4 factors from the 223-chart proof:

| Factor | What it checks | +1 point |
|--------|---------------|----------|
| **Strong Displacement** | Engulfing candle body > 1.2× ATR, or avg body (5 bars) > 0.8× ATR | Yes = +1 |
| **FVG Nearby** | Fair Value Gap within 2× ATR of current price | Yes = +1 |
| **HTF Aligned** | Trade direction agrees with selected HTF trend | Yes = +1 |
| **Not Consolidation** | ATR5/ATR50 ratio above threshold (market is moving) | Yes = +1 |

| Grade | Points | Meaning | Action |
|-------|--------|---------|--------|
| **A+** | 4/4 | All filters pass. Highest conviction. | **TAKE THIS TRADE** |
| **A** | 3/4 | One factor missing. Strong setup. | Take it, but note which factor is missing |
| **B** | 2/4 | Two factors missing. Marginal. | **SKIP or reduce size** |
| **C** | 0-1/4 | Most factors missing. Low quality. | **DO NOT TRADE** |

**The 223-chart backtest showed:**
- Trades with ALL criteria met: ~100% win rate
- Trades missing HTF alignment: ~73% loss rate
- Trades with weak displacement: ~100% loss rate

**Rule: Only trade A+ and A grades. Skip B and C entirely.**

---

## 9. TRADE OUTCOME TRACKING <a name="9-outcome-tracking"></a>

The indicator tracks every signal's result automatically:

### How it works:
1. Signal fires → entry, SL, TP, RR are recorded
2. On each subsequent bar, the indicator checks if price hit TP (WIN) or SL (LOSS)
3. If "Auto Move SL to Breakeven" is ON and price moves ≥1.5R in favour → SL moves to entry
4. If price hits moved SL → result is BE (breakeven, 0R)

### Monthly Stats Table (bottom-right corner)

```
◆ Period | W | L | BE | WR% | BE% | R
May 2026 | 5 | 2 | 1  | 63% | 13% | +8.2R
Apr 2026 | 7 | 1 | 0  | 88% | 0%  | +14.1R
```

| Column | Meaning |
|--------|---------|
| W | Wins (TP hit) |
| L | Losses (SL hit) |
| BE | Breakevens (moved SL hit at entry) |
| WR% | Win rate: W / (W+L+BE) |
| BE% | BE rate: BE / (W+L+BE) |
| R | Total R-return: sum of all trade RRs. Each win = +RR, each loss = -1R, each BE = 0R |

**Important:** The outcome tracker counts ALL signals that fire — including B and C grades. If you follow the grading system (only trade A+ and A), your real results will be better than what this table shows.

---

## 10. RECOMMENDED SETTINGS BY PROFILE <a name="10-recommended"></a>

### EURUSD — Optimal Settings

```
Logic Timeframe:          5
Entry Mode (London):      Auto (or 2nd only)
Entry Mode (NY):          Auto
Max Signals/Session:      1
Max NY Signals:           1

HTF Alignment (legacy):   Off (no filter)
Edge HTF Gate Mode:       Block Counter-Trend
Edge HTF Source:          Both must agree
NY Sell HTF Gate:         Block if HTF Bullish

Consolidation Mode:       Warn
FVG Require:              OFF (badge only)
Show Signal Grade:        ON

Min Body %:               0.85 (T1) / 0.80 (T2)
Min RR:                   2.5
Max RR:                   4.0
SL Buffer:                10 ticks
Vol Confirm:              1.0× (override ON)

BE Auto-Move:             ON at 1.5R
```

### XAUUSD (Gold) — Optimal Settings

Same as EURUSD except:
```
Displacement is auto-boosted by Gold profile (+30%)
T2 Displacement:          1.50× ATR (auto via profile)
SL Min Distance:          0.50× ATR (auto via profile)
Manip Wick:               0.15× ATR (auto via profile)
Max Asia Ticks:           4000 (auto via profile)
Max NY Ticks:             4000 (auto via profile)

Consider: Consolidation Mode = Block (Gold consolidation is especially dangerous)
Consider: FVG Require = ON (86% of Gold wins had FVG)
```

---

## 11. TROUBLESHOOTING <a name="11-troubleshooting"></a>

### "No signals are firing"
1. Check session times — are you in a killzone? Dashboard shows session name.
2. Check if sweep happened — Live Watch shows sweep status
3. Check HTF gates — if 30m and 4H disagree, signals are blocked. Dashboard Edge row shows `HTF:⚪` (neutral)
4. Check Asia Range — if ⚠⚠ HUGE or ✗ BLOCKED, Asia was too wide
5. Check signal limit — "Signals: 1/1" means the session limit is hit

### "Too many signals, most are losses"
1. Set Logic TF to **5** (not 15)
2. Turn ON Edge HTF Gate = Block Counter-Trend
3. Only trade **A+** and **A** grades — skip B and C
4. Set Consolidation Mode to **Block** instead of Warn

### "Monthly stats show poor results"
The outcome tracker counts ALL grades. Your actual results should only include A+/A trades. The tracker will improve if you:
1. Turn Consolidation to Block (removes C-grade signals from tracker)
2. Edge HTF Gate already blocks counter-trend signals
3. The remaining B-grade signals bring down the average

### "Dashboard shows HTF Allows: OFF"
This is the legacy HTF system — it's fine to leave OFF. The v9.25 Edge HTF Gate is the active system. Check the Edge v9.25 row instead for `HTF:🟢/🔴/⚪`.

### "Signal grade shows B but everything looks right"
Check which factor is missing:
- No ✦FVG badge → FVG not nearby (one factor lost)
- HTF:⚪ → HTF is neutral, not aligned (one factor lost)
- ⚠CONSOL → market consolidating (one factor lost)
- Missing displacement → candle body was weak (one factor lost)

If only FVG is missing, the trade can still be valid (A grade). If HTF or displacement is missing, strongly consider skipping.

### "Compilation error: CE10295 too many tokens"
The script is at the Pine v6 token limit. Do not add more code without removing something else.

---

## DAILY WORKFLOW

```
1. Before London opens:
   □ Check dashboard: 30m + 4H trend direction
   □ Note Asia Range size (✓ OK / ⚠ WIDE / ✗ BLOCKED)
   □ Decide: is today a trading day? (no major news, Asia not huge)

2. During London killzone (09:00-11:15 CET):
   □ Watch for sweep (Live Watch panel: Sweep Mem updates)
   □ Wait for engulfing candle
   □ When signal fires → read the label:
     - Grade A+ or A? → TAKE the trade
     - Grade B or C? → SKIP
     - Check SL source, RR, warnings
   □ If signal fires and you enter: monitor the RR box

3. During NY killzone (14:30-17:00 CET):
   □ Check NY Engine status in dashboard
   □ NY requires London sweep first
   □ Same grading rules: only A+/A trades
   □ Be extra cautious with NY shorts (check HTF gate)

4. After session:
   □ Check monthly stats table (bottom-right)
   □ Review any B/C signals that fired — were they correctly skipped?
   □ Note any missed A+ signals — was there a setting issue?
```

---

*Built from 223 chart analyses: 70 EURUSD London, 70 EURUSD NY, 27 XAUUSD NY, plus 56 NO_TRADE days correctly identified.*
