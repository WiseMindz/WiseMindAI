# 🧠 INDICATOR HANDOFF — the middle brain (Claude Code ⇄ Cursor)

**This file is the single source of truth for the WiseMind INDICATOR work** (the Pine Script v6
indicators in this repo: `wise_london_v1.pine`, `wise_ny_v1.pine`, `wisemind_apex_v1.pine`).
Both Claude Code and Cursor **read it at the start of every session** and **update it at the end of
every work slice**. If this file and your memory disagree, **this file wins.**

> Keep it lean but complete. It logs **everything we've done, are doing, and will do** so whoever picks
> up next is instantly oriented. Big-picture ecosystem map (bot + Core + Brain + HQ) lives in
> `~/AI Coding/CLAUDE.md`. Deep indicator design specs live in the playbooks listed in §0.

---

## 0. Read order (do this first, every time)
1. **This file** (`docs/HANDOFF.md`) — current state + full history + next-task queue.
2. `~/AI Coding/CLAUDE.md` — full ecosystem map (bot, Core, Brain, HQ, rules, env vars).
3. `docs/BACKTEST_NOTES.md` — the evidence ledger (the *"why"* behind every filter; cite it before
   proposing filter changes).
4. `WISE_LONDON_V1_SPEC.md` — complete London v1.0 technical spec (26 sections).
5. `WISE_INDICATOR_v925_PLAYBOOK.md` — the v9.25 base logic both split indicators came from.
6. `WISE_SPLIT_PLAYBOOK.md` — why/how the monolith was split into London + NY.

---

## 1. Hard rules (NON-NEGOTIABLE — both tools obey)
- **CONFIRM BEFORE CHANGES.** Michael's standing rule: *"always confirm with me so you understand"* and
  *"be as precise as possible and don't make any mistakes — this is my life work."* Present a plan and get
  a yes **before** editing any `.pine` file. Never edit blindly.
- **Compile clean = 0 errors before "done."** Every Pine change is pushed and confirmed
  `✅ Compiled clean — 0 errors` (see §2). No "this should work."
- **CE10117 compiled-token limit is real.** Pine has a hard compiled-token ceiling. Keep tooltips trim;
  if a build hits CE10117, the fix is to shorten input tooltips / remove dead code (see git history:
  `trim tooltips to stay under CE10117`, `remove dead quality gate code`).
- **All settings must be adjustable from Michael's side.** Every new behavior gets an `input.*` toggle/
  value with a clear tooltip. Never hardcode a threshold he might want to tune.
- **EURUSD behavior must stay unchanged when adding Gold/other-symbol features.** New logic is gated by a
  toggle or scoped to a symbol profile so existing EURUSD results don't move.
- **Keep `maxSignalsPerSession` / `nyMaxSignals` = 1** on both indicators unless told otherwise — Michael
  wants clean charts (1 trade per session). Loosen *quality* filters, not the per-session cap.
- **Secrets:** never hardcode API keys / tokens; never commit `.env`.

---

## 2. Run & verify — the TradingView push workflow
The push tooling lives in `~/tradingview-mcp-jackson/`. To push a `.pine` to the live chart:

```bash
# 1. Stage the source
cp ~/wisemind-ai/wise_ny_v1.pine ~/tradingview-mcp-jackson/scripts/current.pine
# 2. (via TradingView MCP) open the Pine editor + focus it, then:
cd ~/tradingview-mcp-jackson && node scripts/pine_push.js
# 3. Expect: "Pushed N lines → Pine editor / ✅ Compiled clean — 0 errors"
# 4. Save: Ctrl+S (Cmd+S on Mac)
```

**Injection-failure fix (common):** if `pine_push.js` prints `Could not inject into Pine editor`:
1. Close any open indicator **Settings** dialog (`ui_click text "Cancel"`) — it steals focus.
2. `ui_open_panel pine-editor open`, then `ui_click class-contains "monaco-editor"` to confirm the
   editor is actually rendered.
3. Re-run `node scripts/pine_push.js`. (Pressing the `/` key opens **Settings**, not the editor, when the
   chart has focus — don't rely on it.)

**Offline syntax sanity (no TradingView):** you can't truly compile Pine offline, but you can eyeball
balanced `if/else`, matched brackets, and that every new var is declared before use. Real verification =
the in-editor compile above.

---

## 3. CURRENT STATUS  ⬅️ update this section every slice
**Both indicators are split out of the v9.25 monolith and live on TradingView.** Latest builds compiled
clean and are saved.

### `wise_london_v3.pine` — **Wise London v3.0** (NEW 2026-06-04) — ⏳ NOT YET COMPILED by Michael
Copy of `wise_london_v2.pine` → **`~/Downloads/wise_london_v3.pine`** (v2 kept). = v2 + a whole **NY-liquidity
layer built from scratch** (London v2 had ZERO NY tracking — only Asia/PD/PW). Michael's model: a NY-high
sweep (BSL grab) biases London SHORT; a NY-low sweep (SSL grab) biases LONG — same reversal logic as Asia.
London runs before NY each day so it sweeps the PRIOR completed NY (same-day-after or next-day). **CONTEXT
ONLY — does NOT change London's Asia/PD/PW entry triggers → EUR performance intact** (Michael chose "show +
detect", not "tradeable"). Added: `nySess` input (0830-1100); `inNY/nyStarted/nyEnded`; `showNYBox` toggle
(OFF by default) + `nyBoxColor`; NY box tracking; `prevNyHigh/Low` captured at **NY END** (mirrors v5);
`prevNy*SweptToday` flags reset at nyEnded; **all-day** PNY sweep detection → labels **`BSL ✕ PNYH`** /
**`SSL ✕ PNYL`** (external liquidity); `nySweepBias` var → new dashboard row 24 "NY Sweep" (▲ long / ▼ short),
table extended 24→25 rows. Verified: all vars/scope OK, deps exist, no dup nyHigh, top-level placement. **NOT
compiled.** Mirrors v5's PNY logic + London v2's structure (both compiled-clean patterns).
**PNY REFINEMENT (2026-06-05, applied to BOTH wise_ny_v5 + wise_london_v3):** per Michael — (a) chart labels
simplified `BSL ✕ PNYH`/`SSL ✕ PNYL` → just **`PNYH`/`PNYL`** (BSL/SSL stays a concept in London's dashboard
bias row, not on labels); (b) added **rolling forward target lines**: at NY close, delete the old PNYH/PNYL
line+label pair and draw fresh dashed lines at the new prev-NY levels, extended each bar — so the levels are
SHOWN continuously until the next NY close rolls them (`pnyhLine/pnylLine/pnyhLbl/pnylLbl` vars); (c) added a
visible **`Sweep NY H/L` toggle** to the Sweep Detection group in BOTH (London Michael flagged it was missing)
— gates `canDetectPnySweep` + the line draw. Verified both files: 0 stray `BSL ✕`/`SSL ✕` in code, toggle +
gate + rolling-line vars present. Still NOT compiled.

### `wise_london_v2.pine` — **Wise London v2.0** (NEW 2026-06-04) — ⏳ NOT YET COMPILED by Michael
Fresh copy of `wise_london_v1.pine` → **`~/Downloads/wise_london_v2.pine`** (v1 untouched). Ports ALL the NY
v3+v4 work to London so both engines are aligned. **9 changes, EURUSD firing logic UNCHANGED** (only display/
sync/tag + gold + symbol-list touched — what FIRES on EUR is identical). Michael's scope: apply in general
(esp EUR), **remove GBP/CHF** (mains = EUR + XAU), **gold HTF stays Off**. Done: (1) chart-TF dashboard+alert
sync (`chartBullBodyPctV2/chartBearBodyPctV2/chartVolMultV2/chartTfStr`; dashboard Vol+Engulf rows + JSON
`engulf_body_pct`/`vol_spike` repointed); (2) freeze-at-fire toggle `freezeQualityAtFire` (gVis) +
`showEngPctV2/showVolV2/frozen*`; (3) correct TF tag — 4 hardcoded `1m-V1/V2`→`chartTfStr+"-V1/V2"`, `5m`→
`chartTfStr`, `tf_type`→`chartTfStr`; (4) **Asia**-sweep break-and-hold toggle `asiaBreakHoldCounts` + new
`isAsiaSweepHigh/Low` (PD/PW keep strict `isSweepHigh/Low`); (5) gold displacement double-count
`edgeGoldDisplaceBoost` 1.3→1.0; (6) SL buffer + Min FVG profile-aware (`slBufferEff`/`minFvgTicksEff` +
`profileSlBuffer`/`profileMinFvgTicks`); (7) vol-override leak closed (`volConfirmMult = useCustom ? manual :
preset`); (8) gold tuning XAU preset — vol 1.20→1.05, SL 0.50→0.70, Asia cap 4000→6000 (body already 0.80, no
killzone shift — London session fixed); (9) **GBP/CHF removed** — dropdown options, `isGbp/ChfSymbol`,
`useGbp/ChfPreset`, all profile ternaries, display/label tags, titleBg → EUR/XAU/Custom only. Verified: scope/
order OK (drawDashboard def 2765 > freeze 2177), 0 dangling refs, 0 hardcoded 1m. **NOT compiled** — Michael
compiles next (EUR=Custom or Auto, gold=Force XAUUSD, alert on 5m chart). Mirrors NY v3 patterns that compiled
clean. Same bot impact as NY: correct TF tag means 5m-chart London fires now tag `5m` → bot executes them.

### `wise_london_v1.pine` — **Wise London v1.0** (~3022 lines) — superseded by v2 (kept as backup)
London session engine (09:00–11:15 CEST). T1 (immediate reversal) + T2 (AMD retrace), 1 signal/session.
**Shipped this session:**
- ✅ **13 "loosening" changes** (fewer blocked trades, T1/T2 no longer fight): `minBodyRatio` 0.90→**0.80**;
  `requireEngulf` true→**false**; `volConfirmMultManual` 1.5→**1.2**; `t2BodyRatio` 0.85→**0.80**;
  `t2MinRR` 2.5→**2.0**; `minRR` 2.5→**2.0**; `pdTouchWindow` 15→**20**; `maxDistanceAtr` 1.0→**1.5**;
  `enableLowVolFilter` true→**false**; **removed** `oneSignalPerSide` + `oneT2PerSide` inputs; **removed**
  the "v9.3 Directional Sweep Memory Filter" block; **simplified** `longBase`/`shortBase`.
- ✅ **Label cleanup** — removed `ASIA WIDE` + `FVG` badges and the `[path]` tag from fired-trade labels;
  rows are narrower. Kept only the grade badge (A+/A/B/C).
- ✅ **Live Watch "Sweep Mem" row** renamed **"Swept"** showing AL/AH/BOTH.
- ✅ **24h auto-close** (see "Shared feature" below).
- Kept `maxSignalsPerSession = 1`.

### `wise_ny_v5.pine` — **Wise NY v5.0** (NEW 2026-06-04) — ⏳ NOT YET COMPILED by Michael
Copy of `wise_ny_v4.pine` → **`~/Downloads/wise_ny_v5.pine`** (v4 kept). = v4 + **Prev-NY-liquidity (PNYH/PNYL)
sweep fix** Michael caught: chart was littered with stale "Sweep PNYH/PNYL" marks because the prev-NY level
was captured a session too late and never reset cleanly. Fixes (confirmed: base v4, detect ALL DAY incl Asia,
label as BSL/SSL external): (1) added `nyEnded = not inNY and inNY[1]`; (2) **capture `prevNyHigh/Low` at NY
END** (was at `nyStarted` = a session stale during the next day's Asia/London) — removed the nyStarted capture;
(3) reset `prevNyHigh/LowSweptToday` + `pnyh/pnylSweptBar` in the nyEnded block (removed from `asiaStarted`) so
the NEW level starts unswept; (4) `canDetectPnySweep` = drop `not inAsia` → detect any time, every session +
off-hours; (5) labels `Sweep PNYL/H`→**`SSL ✕ PNYL`** / **`BSL ✕ PNYH`** (PNYH=external buy-side, PNYL=external
sell-side liquidity). Verified scope/assignments. **NOT compiled.** Concept confirmed w/ Michael: PNYH/PNYL =
EXTERNAL liquidity (BSL above highs, SSL below lows); FVG/OB = internal.
**↳ NEXT (Michael's ask, NOT yet built — needs confirm):** port this PNY fix to **London → create
`wise_london_v3.pine`**, BUT London v2 has NO NY-session tracking at all (only Asia/PD/PW) — so it's port + ADD
NY box + nyHigh/Low + prevNy capture/detect. London runs before NY each day so it sweeps the PRIOR completed
NY (same-day-after or next-day). Michael: "NY box must show in London too."

### `wise_ny_v4.pine` — **Wise NY v4.0** (NEW 2026-06-04) — ⏳ NOT YET COMPILED by Michael
Fresh copy of `wise_ny_v3.pine` → **`~/Downloads/wise_ny_v4.pine`** (v3 untouched as backup). v4 = all v3
fixes PLUS **gold isolation** so XAUUSD stops running on EURUSD values. Michael caught it: on a gold chart
the header read `CUSTOM ⚙ MANUAL` and gold got `NY Status ✗ BLOCKED London>500tk` / `Asia 3384tk BLOCKED`
because Custom mode fed EUR tick caps (500) to gold. **Workflow:** Michael keeps EURUSD on **Custom** (his
tuned manual values) and **manually switches the profile to "Force XAUUSD"** for gold. The profile system
already isolates symbols (EUR preset vs XAU preset are independent constants; Custom uses the manual inputs)
— v4 just plugs the leaks so switching to Force XAUUSD = fully gold-tuned, **zero EUR leak, EURUSD untouched.**
**4 XAU-side fixes (ratios stay shared — they're symbol-neutral):**
1. **Gold tick caps 4000→6000** — `profileMaxAsiaTicks` + `profileMaxNyTicks` (XAU only; EUR stays 500). Gold
   ranges $40-60 (4000-6000 ticks) so 4000 over-blocked NY.
2. **SL buffer now profile-aware** — new `profileSlBuffer` (XAU 80tk=$0.80, EUR 15) + `slBufferEff`; all 6 SL
   usages repointed. Was a flat 15tk for all symbols (=$0.15 on gold, too tight).
3. **Min FVG size profile-aware** — new `profileMinFvgTicks` (XAU 30tk, EUR 4) + `minFvgTicksEff`. Was flat 4tk
   (=$0.04 on gold → filter did nothing, micro-FVG noise).
4. **Vol-confirm leak closed** — `volConfirmMult = useCustom ? manual : profileVolConfirm` (was `(useCustom or
   overrideVolConfirmMult) ? manual : preset`). Now a symbol profile WINS; the override only acts in Custom.
   Gold no longer keeps EUR's 1.25 — uses XAU preset 1.15.
**Untouched & correct:** body% / RR / vol-ratio / all ×ATR filters are shared across symbols (symbol-neutral
by design). EUR preset constants + Michael's Custom manual inputs: 0 changes. **Verify:** structural checks
pass (no bare `slBuffer`/`minFvgSizeTicks` left in logic, scope/order OK, gold caps=6000). **NOT compiled** —
Michael compiles next; if clean, v4 becomes the live NY indicator (EURUSD=Custom, gold=Force XAUUSD).
**v4 is the TEST pine** (Michael's call 2026-06-04). **2 more defaults baked from his panel:** `enableBEMove`
true→**false** (Auto-BE off — indicator-only, BOT still does real BE @2R; makes perf table raw W/L);
`htfAlignMode` "Off"→**"30m OR 4H must agree"** (real filter, cuts signals on EUR+gold). **GOLD UNDERPERF
INVESTIGATION (briefed, fixes NOT yet built — awaiting Michael's go):** gold tables ~bad (Apr 0W/3L, May
1W/2L, Jun 0W/1L) vs EUR strong (+16R, +8.9R). Root causes IDENTIFIED in code: (1) 🔴 **displacement
double-count** — `t2DisplaceAtrBuy = t2DisplaceAtr(XAU 1.50) × goldBoost(1.3) = 1.95×ATR`; short =
×1.40 sell-boost too = **2.73×ATR** vs EUR 1.25/1.75. Gold already raised in the preset, then `goldBoost`
raises it AGAIN → gold T2 rare + enters at exhaustion → losses. Proposed fix A: **Gold Displacement Boost
1.3→1.0** (test alone first). (2) 🟠 HTF filter now ON + gold's laggy/news-whipsawed 4H bias → forces
counter-trend (e.g. shorts-only on a rising day). Proposed fix B: gold-aware HTF (4H-only/Off on XAU).
(3) structural: NY killzone 0830-1100 ET = US-news whipsaw window for gold; spread not in backtest; ~9-trade
sample = high variance. Plan: test fix A in isolation first. **STATUS 2026-06-04: Michael CONFIRMED fix A (Gold Displacement Boost
1.3→1.0) — but it is NOT yet applied to the file:** macOS revoked this process's read/write access to
`~/Downloads` mid-session (`Operation not permitted` on every Downloads file; `ls` works, project dir
`~/AI Coding` still fine — it's a TCC/Full-Disk-Access block on the protected Downloads folder). The 2 deltas
(BE off, HTF) WERE saved before the block. To finish: Michael either (a) sets Gold Displacement Boost=1.0 in
the TradingView panel to TEST now, and/or (b) grants Full Disk Access then says "retry" so the code default
is baked, or (c) moves the `wise_ny_*.pine` files into `~/AI Coding/wisemind-ai/` (accessible) for future
edits. NEXT ACTION when unblocked: edit `edgeGoldDisplaceBoost` input default 1.3→1.0 in wise_ny_v4.pine.
**✅ DONE 2026-06-04 (Downloads access restored after FDA grant): FULL GOLD PRESET built into wise_ny_v4.pine**
(Michael chose all-6-at-once). All XAU-side, EUR untouched: (1) `edgeGoldDisplaceBoost` 1.3→**1.0** (double-count
killed); (2) `profileVolConfirm` XAU 1.15→**1.05**; (3) `profileSlMinAtr` XAU 0.60→**0.70**; (4) gold NY killzone
via `nySessEff = useXauPreset ? "0900-1100" : nySess` (skip 08:30 spike); (5) gold HTF via `htfAlignModeEff =
useXauPreset ? "4H only" : htfAlignMode`; (6) gold body via `nyT1BodyRatioEff`/`nyT2BodyRatioEff` (XAU 0.80).
New gold-effective vars added + all usages repointed; verified 0 bare `htfAlignMode ==` / 0 bare body-ratio
checks left, scope order OK. **NOT compiled** — Michael compiles next. ⚠️ Methodology caveat (told Michael):
6-at-once means if results change we won't know which fix did it; #6 body% is the most debatable (looser = weaker
setups) — revert first if gold quality drops. Need a real test-week sample (>9 trades) before judging.

### `wise_ny_v3.pine` — **Wise NY v3.0** (2026-06-04) — superseded by v4 (kept as backup)
Fresh copy of `~/Downloads/wise_ny_v.2.pine` → **`~/Downloads/wise_ny_v3.pine`** (v2 left 100% untouched as
backup). Built to fix a dashboard/fire **desync** Michael caught: a `1m-V2` precision fire on a 5m chart
gated body ≥80% on the **chart candle**, but the dashboard "Engulf Body" + "Vol Strength" rows + the alert
JSON read the **15m logic candle** (`eff*`) → showed 62% while the fire used a ≥80% candle. **Four fixes
(all confirmed by Michael, two as toggles):**
1. **Dashboard + alert JSON now read the CHART-TF candle** (1m chart→1m candle, 5m→5m), the SAME candle the
   fire gate checks → dashboard = fire = bot, always synced. New globals `chartBullBodyPctV3 /
   chartBearBodyPctV3 / chartVolMultV3 / chartTfStr` (after `effVolMult`). Dashboard rows (Vol Strength,
   Engulf Body) + JSON `engulf_body_pct` / `vol_spike` repointed to these.
2. **Freeze Signal Quality at fire** — input `freezeQualityAtFire` (gVis, default ON): live while watching,
   snapshots the firing candle's exact body%/vol the moment a trade fires (`frozenEngPctV3/VolV3`,
   `showEngPctV3/showVolV3`), resets at new NY session.
3. **Correct TF tag** — `lastFireTfTag` now uses `chartTfStr` (e.g. `5m-V2` on 5m, `1m-V2` on 1m) instead of
   hardcoded `"1m"`; JSON `tf_type` = `chartTfStr`. ⚠️ **BOT IMPACT:** this makes `EXECUTE_ONLY_5M` work by
   chart TF — a fire from a **5m chart** tags `5m` → **bot trades it**; from a **1m chart** tags `1m` → bot
   skips. So Michael must run the live TradingView alert on the **5m chart** for execution.
4. **London sweep toggle** — input `londonBreakHoldCounts` (gSwp, default OFF = strict close-back). ON = a
   clean break that HOLDS above/below the London H/L also counts as swept. New helpers
   `isLondonSweepHigh/Low` (Asia/PD/PW still use the strict `isSweepHigh/Low`).
**Verify:** structural checks pass (var scope/order OK, no hardcoded `1m` tag, London detection uses new
helpers). **NOT compiled** — Michael compiles on TradingView next. If clean, this supersedes v2 as the live
NY indicator (alert on 5m chart).

**Defaults baked from Michael's live settings (2026-06-04, read off his TradingView Inputs panel):** 6
deltas from the v2 code defaults → now v3 ships pre-tuned: `profileOverride` Auto→**Custom (manual values)**;
`oneMinBodyRatio` (1m T1) 0.80→**0.75**; `obMinMoveAtr` (Order-Blocks Min Displacement) 1.0→**1.5** (his ask;
T2 min displacement stays **1.25** — initially mis-set to 1.5, reverted); `pdTouchWindow` 15→**20**;
`volConfirmMultManual` 1.5→**1.25**; `beThresholdR` 1.5→**2.0**. Everything else
already matched. ✅ **BOT SYNC DONE (2026-06-04):** Michael set Railway **`BE_TRIGGER_R=2.0`** — real-account breakeven now
matches the indicator's 2R. ⚠️ `profileOverride=Custom` disables EURUSD/XAU
auto-tuning (uses manual values for ALL symbols) — fine for EURUSD, but gold would use EUR-tuned values.
**Monthly stats note (briefed):** the indicator perf table recomputes live over LOADED bars only; a 5m chart
loads ~2-3 months, so older/worse pre-April months only appear when you scroll back. Recent-months-look-great
= recency/curve-fit yellow flag; weight full history, the bot guards stay on.

### `wise_ny_v1.pine` — **Wise NY v2.0** (~2611 lines) — LIVE (functional), compiles clean
NY session engine (08:30–11:00 ET / 14:00–17:00 CEST). Same T1/T2 + 1m fire as London, plus Gold/PO3 work.
**Shipped this session (the "make Gold work as well as EURUSD" update):**
- ✅ **Prev-NY High/Low (PNYH/PNYL) sweep targets** — captures yesterday's NY high/low; arms SHORT on a
  PNYH sweep / LONG on a PNYL sweep, then runs T1/T2. NY sweep priority per side: **London → Prev-NY →
  Asia fallback**. New toggles `nyAcceptPNYH` / `nyAcceptPNYL`. (This is the #1 gold pattern: "sweep of
  Prev-NY highs then PO3.")
- ✅ **15m + 30m FVG now count as PD-touch retrace zones** — `touchedBullPdNy`/`touchedBearPdNy` extended
  to scan the 15m & 30m FVG arrays (gated by new `nyZone15m` / `nyZone30m` toggles, both default ON).
  Before, only 5m FVG + OB qualified, so gold setups that retrace into a 15m/30m FVG silently failed.
  Also **fixed a latent array-cleanup bug**: 15m/30m FVG boxes/arrays are now pushed in lockstep (a `na`
  box when display is off) so the existing delete/trim loops keep the logic arrays fresh even when the
  zones aren't drawn. OB is single-TF (built on the logic TF, 15m by default) so "15m OB" already counts.
- ✅ **PO3 badge** — labels show `PO3 A→M→D` once London or Prev-NY manipulation liquidity was swept
  before the NY entry. Display-only (`showPo3Badge`), no filtering.
- ✅ **XAU profile tuned** — manip wick 0.15→**0.18** ATR, SL min-dist 0.50→**0.60** ATR, vol confirm
  1.20→**1.15**× (gold tick-volume is noisy); T2 displacement stays 1.50. All overridable via profile =
  Custom.
- ✅ **24h auto-close** (shared feature below).
- ✅ **Title bumped to "Wise NY v2.0"** in code.
- Kept `nyMaxSignals = 1`.

### Shared feature shipped this session — **24h Auto-Close (time expiry)** (both indicators)
New input `tradeExpiryHours` (default **24**, range 1–168, `0` = off) under *◆ Trade Outcome Tracking*.
If a fired trade hasn't hit SL/BE/TP after N hours of chart time, it's **force-closed at market**:
computes **actual RR** (+ = win, − = loss) and **P&L %**, marks the chart label
`⏱ 24H CLOSE / WIN|LOSS / +1.23R | +0.45%` (green win / red loss), adds it to the monthly stats, and
emits a JSON webhook alert `"event":"trade_expiry"` with `rr_achieved`, `pnl_pct`, `closed_by`.
Implemented via a new `outcomeFireTime` var captured at entry; expiry checked right after the SL/TP
detection block.

### Known-good / saved copies
- TradingView: **Wise London v1.0** saved; **Wise NY** saved (functional v2; on-chart title push of the
  "v2.0" string is the one cosmetic item still pending — see §5).
- Downloads backups: `~/Downloads/wise_london_v1.pine`, `~/Downloads/wise_ny_v.2.pine` (refresh these
  whenever you hand Michael a file — he applies updates manually too).

### Infra notes verified this session (not indicator code, but context)
- **Anthropic API was out of credits** → bot "couldn't answer." Michael added credits → **resolved.**
- **Signal flow:** TradingView → bot `/webhook` → (1) `trades.db`, (2) Telegram, (3) **WiseMind HQ** *only
  if* `WISEMIND_HQ_URL` is set in the bot's Railway vars. Signals do **NOT** go to WiseMindBrain (local).
  HQ dashboard + its `/webhook` are live (`wisemind-hq-production.up.railway.app`).
- `TELEGRAM_CHAT_ID` is **blank in local `.env`** (would crash local startup; on Railway it may be set).
- `config.py` line 29 `CLAUDE_MODEL_SMART = "claude-sonnet-4-6"` — **verify this model ID is valid** when
  credits are live; if `model_not_found`, use `claude-sonnet-4-5`.

---

## 4. How the indicators actually work (orientation for whoever picks up)
- **Two entry types:** **T1** = immediate reversal at swept liquidity + strong engulf. **T2 (AMD)** =
  sweep → displacement (≥ x·ATR) → retrace into a PD zone (FVG/OB) → engulf.
- **PO3 frame:** Asia = Accumulation, London = Manipulation, NY = Distribution.
- **Sweep targets:** London H/L, Asia H/L, Prev-NY H/L (NY only), PDH/PDL, PWH/PWL — each toggle-gated.
- **PD zones (retrace targets):** 5m FVG + OB always; NY also 15m/30m FVG (toggle). Bull FVG bounds:
  top=`*Tops` array, bottom=`*Bots`; bear FVG: top=`*Tops`, bottom=`*Bots` (verified — arrays store
  upper price in `Tops`, lower in `Bots`, consistent across 5m/15m/30m).
- **Multi-TF logic:** all strategy logic runs on `logicTF` (default 15m NY / per London spec) via
  `request.security`, independent of chart TF. **1m Precision Fire** fires on 1m engulfs inside an active
  setup when chart TF < logic TF (Variant 1 = synchronized, Variant 2 = independent).
- **Smart SL chain:** engulf → swing → session H/L → prev-session fallback. **Smart TP:** nearest level in
  the target RR band from the enabled candidate pool.
- **Symbol Auto-Profile:** EURUSD / XAUUSD presets auto-applied from ticker; `Custom` unlocks manual values.
- **Grade:** A+/A/B/C from displacement, FVG presence, HTF alignment, consolidation.
- **Outcome tracking:** SL/TP/BE detection + monthly stats + (new) 24h auto-close, all emit JSON alerts.

---

## 5. NEXT TASK QUEUE  (do top-first; CONFIRM before editing — see §1)
1. **EURUSD NY backtest validation** — Michael is sending **EURUSD NY session backtest screenshots**.
   Use them to validate the NY engine (esp. PNYH/PNYL + 15m/30m zones) and fine-tune thresholds. _(Top —
   waiting on his screenshots.)_
2. **Push the "Wise NY v2.0" title to the chart** — cosmetic; the functional v2 is already live. The Pine
   editor injection was glitchy (Settings dialog stealing focus) — retry per §2.
3. **London sell gate** — add `londonSellGate` ("Off" / "Block if HTF Bullish" / "Require HTF Bearish"),
   mirroring NY's `edgeNySellGate`. Backtest finding: AH sweeps = 52% of losses but only 35% of wins.
4. **London late-entry gate** — `minBarsBeforeSessionEnd` (don't fire in the last N bars of London; late
   entries fail more in the backtest).
5. **Gold RR cap** — some gold NY moves hit 5.2R but `maxRR`/`t2MaxRR` cap at 4.0. Consider a separate
   gold cap (don't change the global default — it affects EURUSD).
6. **Grade-penalty system** — auto-downgrade both-sides-swept (−1) / no-FVG (−1) / counter-trend (−1),
   boost clean strong 1st entry (+1).

> Backtest evidence for items 3–6 lives in the London analysis (40W/27L/4BE = 56.3% WR; both-sides-swept
> = 2.4× more likely in losses; FVG = 1.5× more likely in wins; projected ~65–70% WR with these gates).

---

## 6. Handoff protocol (the "automatic middle brain")
When you finish a slice, **before ending the session**:
1. Move the shipped item into **§3 Current status** (with the exact param/line-level detail + "compiles
   clean / saved" state).
2. Re-order **§5 Next task queue** so the top item is the true next thing.
3. If you changed how something works, update **§4**.
4. Refresh the `~/Downloads/` copy if you handed Michael a file.

That's the contract: whoever picks up next (Claude Code OR Cursor) reads §0→§5 and is instantly oriented.
**The file is the shared brain.**

---

## 7. 📋 PASTE-READY RESUME PROMPT (copy into a fresh Cursor / Claude chat)
```
Read wisemind-ai/docs/HANDOFF.md and ~/AI Coding/CLAUDE.md first, then continue the WiseMind INDICATOR
work. Obey HANDOFF §1 hard rules: CONFIRM with Michael before editing any .pine ("this is my life work,
be precise, don't make mistakes"); compile clean (0 errors) before calling anything done; every new
behavior gets an adjustable input; keep EURUSD behavior unchanged when adding gold features; keep 1
signal per session. Push/verify per HANDOFF §2 (stage to current.pine → pine_push.js → expect
"Compiled clean — 0 errors" → Ctrl+S). Pick the top item from HANDOFF §5, propose the plan, and only
build after a yes. When done, update HANDOFF §3 + §5 per §6.
```
