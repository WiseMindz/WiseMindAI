# 🤖 BOT HANDOFF — the middle brain (Claude Code ⇄ Cursor)

**This file is the single source of truth for the WiseMind EXECUTION BOT** — the Python service that
receives TradingView alerts, scores them, and **auto-executes trades on MetaTrader 5 via MetaAPI**, plus
the breakeven monitor and Telegram coach. Both Claude Code and Cursor **read it at the start of every
session** and **update it at the end of every work slice**. If this file and your memory disagree,
**this file wins.**

> Sibling brain: `docs/HANDOFF.md` is the **indicator** middle brain (the `.pine` files). This file is the
> **bot/execution** middle brain. Big-picture ecosystem map lives in `~/AI Coding/CLAUDE.md`.

---

## 0. Read order (do this first, every time)
1. **This file** (`docs/BOT_HANDOFF.md`) — bot state + full history + next-task queue.
2. `~/AI Coding/CLAUDE.md` — full ecosystem map (bot, Core, Brain, HQ, rules, env vars).
3. `docs/HANDOFF.md` — the indicator brain (what the Pine scripts send to this bot).
4. Key bot files: `bot.py`, `webhook_handler.py`, `mt5_executor.py`, `signal_utils.py`, `config.py`.

---

## 1. Hard rules (NON-NEGOTIABLE — both tools obey)
- **CONFIRM BEFORE CHANGES.** Michael's standing rule: *"always confirm with me so you understand"* and
  *"be as precise as possible, don't make mistakes — this is my life work."* Plan → yes → then edit.
- **NEVER auto-trade without an explicit go.** Default `.env` state is **safe**:
  `MT5_EXECUTION_ENABLED=false` + `MT5_DRY_RUN=true`. Only flip to live when Michael says so.
- **Demo first, always.** Account is currently IC Markets **demo** (`ICMarketsEU-Demo`). Prove any change
  on demo before real money. On real money, start `MT5_MIN_GRADE=A+`.
- **Real money = real risk.** If the connected account is switched to live/funded, confirm
  `ACCOUNT_BALANCE` matches the real balance (lot sizing depends on it) and check prop-firm automation
  rules (many ban API/EA trading).
- **Secrets via `.env` only.** Never hardcode the MetaAPI token / Telegram token / Claude key; never
  commit `.env`. (`.env` already holds live secrets — do not paste them into code or docs.)
- **Verify before "done."** Syntax-check every Python change; for execution changes, prove on demo (open
  → observe → close). No "this should work."
- **Pine is the brain; the bot is the hand.** The bot must execute the Pine signal *exactly* (entry/SL/TP
  from the alert). The only things the bot adds: lot size (from balance × risk%), grade filter, and
  breakeven management. Never re-derive entry/SL/TP.
- **DOCUMENT EVERYTHING, ALWAYS — standing order from Michael (no need to be asked).** Every session you
  must keep THIS file fully current: what we did (history), what we're doing (current), and what's planned
  (future — short-term, long-term, roadmap, vision, "maybe later" ideas — ALL of it). Log it here so
  Claude Code and Cursor are always on the same page. If it isn't written here, it didn't happen. Update
  proactively, not just when told.

---

## 2. Run & verify — local workflow
```bash
# Start the bot locally (Telegram + webhook + MetaAPI + BE monitor on one asyncio loop)
cd "/Users/vividvalorm/AI Coding/wisemind-ai"
source venv/bin/activate
python run_LOCAL_DEV_ONLY.py        # auto-restarts on .py save (dev)
#   or:  python bot.py              # plain run

# Expose the webhook to TradingView (separate terminal)
ngrok http 8000                     # → https://XXXX.ngrok-free.app  (use /webhook)
```
**Expected healthy startup log:**
```
✅ Webhook configured: http://0.0.0.0:8000/webhook
✅ Telegram bot polling started
🎯 WiseMind AI is LIVE
✅ MetaAPI: connected and synchronized        (only if MT5_EXECUTION_ENABLED=true)
🔒 Breakeven monitor started — trigger 1.5R…  (only if BE_ENABLED=true)
```
**Manual signal test (no TradingView needed):**
```bash
curl -X POST http://localhost:8000/webhook -H "Content-Type: application/json" \
  -d '{"secret":"wisemind2026","symbol":"EURUSD","side":"LONG","session":"London",
       "entry":1.16330,"sl":1.15830,"tp":1.17330,"rr":2.0,"swept":"AL",
       "after_manipulation":true,"htf_aligned":true,"quality_grade":"A+","version":"9.25"}'
```
**Isolated connection / position checks:** write a tiny script that loads `.env`, calls
`mt5_executor.init_connection(...)`, then `get_positions()` / `close_position()` — proven pattern (used
to open/close/modify test trades on demo this session).

---

## 3. CURRENT STATUS  ⬅️ update this section every slice

**🟢 STAGE 1 LIVE: the bot is DEPLOYED on Railway and trading the IC Markets demo 24/7.**
Deployed `2026-06-02` from GitHub `main` (commit 3fd9ab6) to the `WiseMindAI` Railway service
(`wisemindai-production.up.railway.app`, PORT 8080). Railway vars set: METAAPI_TOKEN/ACCOUNT_ID,
`MT5_EXECUTION_ENABLED=true`, `MT5_DRY_RUN=false`, `MT5_MIN_GRADE=B`, `ACCOUNT_BALANCE=100000`, all BE_*/
EXPIRY_*/MAX_TRADES_PER_DAY/DAY_RESET_TZ, `WISEMIND_HQ_URL=https://wisemind-hq-production.up.railway.app`.
Deploy logs confirmed: **"✅ MetaAPI: connected and synchronized" + "🔒 Position monitor started — BE
1.5R / expiry 24h / poll 15s"**, account clean (getPositions []). Existing TradingView alerts already point
at this service, so the next real A+/A/B signal auto-executes. (Local `.env` stays safe/off; the LOCAL repo
is for dev only — do NOT run `python bot.py` locally while Railway is live or you get the Telegram 409.)
**Watch:** a transient **Telegram getUpdates 409 Conflict** appears during redeploys (old+new container
overlap) — harmless to execution (webhook+MetaAPI are separate from Telegram polling); resolves when the
old deployment stops. If persistent → a 2nd instance is running (local, or an old Railway deployment still
Active) — kill it.
NOTE: `DAILY_STATE_PATH` not set → daily cap uses ephemeral storage → **count resets on every Railway
redeploy** (could allow a 2nd trade after a deploy). For the demo week this is acceptable; before funded,
add a Railway volume at `/data` and set `DAILY_STATE_PATH=/data/daily_trades.json`.

### Execution path (built this session)
- **`mt5_executor.py`** — MetaAPI bridge:
  - `init_connection()` / `close_connection()` — RPC connection lifecycle (uses
    `account.get_rpc_connection()` → `connect()` → `wait_synchronized()` with **no args**).
  - `should_execute(grade, min_grade)` — grade gate (A+ > B > C; default min **B**).
  - `execute_trade(symbol, side, lot, sl, tp, comment)` — market buy/sell with SL+TP.
    ⚠️ **MetaAPI gotchas fixed:** (1) **no `clientId`** in options (strict pattern, was rejected);
    (2) comment sanitized to `[A-Za-z0-9 _]`, max 25 chars (the `+` in "A+" was rejected).
  - **Position monitor** (`run_position_monitor` / `start_position_monitor` / `stop_position_monitor`,
    with `_check_breakeven_once` + `_check_expiry_once`): one background loop, every `BE_POLL_SECONDS`,
    runs BOTH trade-management features on open positions:
    • **Breakeven** — `R = profit_distance / |entry−SL|`; when `R ≥ trigger` → `modify_position(id,
      SL=entry(+buffer), TP=unchanged)`. Mirrors Pine `enableBEMove`/`beThresholdR=1.5`.
    • **Time-expiry** — uses the broker position `time` (UTC datetime); if open age ≥ `expiry_hours`
      (0=off) → `close_position` at market. Mirrors Pine `tradeExpiryHours=24`.
    • **Per-position parity** — `register_position_settings(order_id, be_trigger_r, expiry_hours)` (called
      from the webhook on a successful execute) lets each position use the values **Pine sent in the alert**
      (`be_trigger_r`/`expiry_hours`); falls back to `.env` defaults when absent. So bot↔indicator
      management settings can never drift. Robust across restarts (skips SL≈entry; prunes closed ids).
    • Verified live on demo: BE moved SL + preserved TP; expiry force-closed a stale position; combined
      monitor boots/stops cleanly.
- **`webhook_handler.py`** — after scoring (`evaluate_signal`) and lot calc:
  - DRY RUN → logs "would execute", no order.
  - LIVE → `should_execute` gate → `execute_trade`. Result is appended to the Telegram message
    (✅ EXECUTED / ❌ FAILED / ⏭️ skipped / 🔬 dry run).
  - **lifespan** starts MetaAPI + BE monitor on boot (live mode) and stops them on shutdown.
- **`safety.py` (Phase 0)** — kill switch + daily loss limit. `is_paused()/set_paused()` (Telegram
  `/pause` `/resume`, admin-gated to `ADMIN_USER_ID`); `check_daily_loss(equity, MAX_DAILY_LOSS_PCT, tz)`
  auto-stops trading for the day at −2% (sticky); `/status` shows live/paused, MetaAPI, trades today, loss
  state, equity. Error alerts ping Telegram on a failed order (`ERROR_ALERTS`). State persisted to
  `bot_state.json` (volume). Tested on demo.
- **`daily_limit.py`** — strict global **daily trade cap** (`MAX_TRADES_PER_DAY`, default **1**). Once the
  day's quota of *executed* trades is reached, the bot **ignores ALL further signals that day** (every
  asset/session/indicator). Only real fills count (grade-skipped/failed don't burn a slot). Count is
  persisted to `daily_trades.json` so a restart can't sneak in an extra trade. "Day" = calendar date in
  `DAY_RESET_TZ` (default `Europe/Stockholm`/CEST). Gate runs inside `daily_limit.LOCK` (held across
  check→execute→record) so two near-simultaneous signals can't both pass. Telegram shows
  "⛔ Daily limit reached (1/1) — signal logged, NOT traded". Verified live on demo: signal 1 executed,
  signal 2 blocked, exactly 1 position opened.
- **`config.py` / `.env`** — keys: `METAAPI_TOKEN`, `METAAPI_ACCOUNT_ID`, `MT5_EXECUTION_ENABLED`,
  `MT5_DRY_RUN`, `MT5_MIN_GRADE`, `BE_ENABLED`, `BE_TRIGGER_R`, `BE_BUFFER_PIPS`, `BE_POLL_SECONDS`,
  `EXPIRY_ENABLED`, `EXPIRY_HOURS` (mirrors Pine 24h auto-close; 0=off), `MAX_TRADES_PER_DAY` (default 1),
  `DAY_RESET_TZ` (default Europe/Stockholm), optional `DAILY_STATE_PATH`.
  ⚠️ **Railway caveat:** put `DAILY_STATE_PATH` on the persistent volume (e.g. `/data/daily_trades.json`)
  or the daily count resets on every redeploy — which would allow a 2nd trade after a deploy.
- **`requirements.txt`** — `metaapi-cloud-sdk>=29`, `anthropic>=0.105`, `httpx>=0.28`, `watchdog`.

### Live demo proof (this session)
- MetaAPI account **WiseMind IC Demo** `bd1c91cb-f3b9-4ea4-a1c1-5ff5a810abdf`, MT5-52879989,
  `ICMarketsEU-Demo`, **Connected**, balance ~$100.5k.
- Fired test signals through the bot → **real trades opened on demo** (e.g. #1678949281 LONG 2.0 EURUSD).
  C-grade correctly **skipped**, A+ **executed**. Telegram messages delivered.
- BE monitor verified: `modify_position` moved SL up and **preserved TP**; all test positions closed
  (account left flat).

### Known issues / watch-outs
- **Telegram polling conflict:** the **Railway** deployment runs the *same* bot token. Running the bot
  locally too triggers `Conflict: terminated by other getUpdates`. Harmless for the webhook/execution
  (sending still works), but execution should ultimately live in **one** place — see §5.
- **Dependency clash (fixed):** installing `metaapi-cloud-sdk` upgraded `httpx` → broke old
  `anthropic 0.37` (`proxies` kwarg). Fixed by upgrading anthropic to ≥0.105. Don't re-pin httpx to 0.27.
- **`entry_price` in execute_trade result is `0`** (SDK response lacks `openPrice` on the market-order
  return) — cosmetic only; order_id/position is correct. Could fetch the position to fill it later.
- **Broker symbol suffixes:** IC Markets uses bare `EURUSD`. A different broker may use `EURUSD.r` etc.,
  which would fail with "symbol not found" → add a suffix map in `mt5_executor` if Michael switches.
- **ngrok URL changes** each restart (free tier) → TradingView webhook URL must be re-pasted. A static
  domain (paid ngrok) or hosting the webhook removes this.
- **HQ grade tiers not yet synced:** the bot is now 4-tier (A+/A/B/C), but `wisemind-hq/server.js`
  `evaluateSignal()` still collapses to A+/B/C. For full system sync, mirror the 4-tier change in HQ when
  we do the HQ merge (§5 item 8). ⚠️ HQ is live on Railway — confirm before editing.

---

## 4. How the bot works AFTER a Pine signal fires (full lifecycle — orientation)

```
TradingView (Wise London v1 / Wise NY v2 / APEX) fires alert()
        │  JSON: secret, symbol, side, entry, sl, tp, rr, session, swept,
        │        after_manipulation, htf_aligned, quality_grade, version, …
        ▼
POST /webhook   (webhook_handler.receive_webhook)
        ├─ verify secret == WEBHOOK_SECRET (wisemind2026) else 401
        ├─ require symbol/side/entry/sl/tp (legacy text alerts parsed as fallback)
        ├─ calculate_lot_size()  → lot from ACCOUNT_BALANCE × ACCOUNT_RISK_PERCENT and SL distance
        ├─ evaluate_signal()     → rating A+/B/C (+ uses Pine quality_grade when present)
        ├─ EXECUTION:
        │     DRY RUN          → log only, no order
        │     LIVE + grade≥min → mt5_executor.execute_trade()  → MetaAPI → MT5 market order (SL+TP)
        │     grade<min        → skipped
        ├─ save_trade() → trades.db
        ├─ format_telegram_message() (+ exec status line) → send to TELEGRAM_CHAT_ID
        └─ (optional) forward to WiseMind HQ if WISEMIND_HQ_URL set
        ▼
Breakeven monitor (background loop, live mode only)
        every BE_POLL_SECONDS: if any open position ≥ BE_TRIGGER_R → move SL to entry, keep TP
        ▼
Position runs to TP or (breakeven) SL on the broker — MetaAPI/MT5 manage the exit
```

### 🎯 Order placement (entry/SL/TP) — verified
Every execution is **one market order with SL + TP attached atomically** (`create_market_buy/sell_order(
symbol, lot, sl, tp)`): entry = market fill (≈ Pine entry, normal slippage possible); **SL & TP = Pine's
EXACT absolute prices**. There is never a naked (stop-less) position — good for prop firms that require a
stop on every trade. Verified live on demo (Pine SL 1.15816 / TP 1.17016 → identical on broker).

### 🏦 FundingTraders rules vs our bot (researched by Michael) — likely ALLOWED, with conditions
FundingTraders allows **self-developed / AI-assisted bots IF you understand the code & helped build it**,
plus risk-management bots. Prohibited: commercial/off-the-shelf bots, **grid, hedging, HFT (<15s repeated
trades), copying another trader's trades via API**. Our bot maps to the ALLOWED profile: custom + built
with Michael (documented here so he can explain it) + risk-managed (1% sizing, 1 trade/day, BE, expiry);
it is **not** grid/hedge/HFT/commercial, and it trades **Michael's own indicator** (not another trader).
The 3 deciding factors: (1) Michael must genuinely understand it (this handoff is the why); (2) **get
written confirmation from FundingTraders support** — the loose rule is "copying another trader's trades via
API"; describe it exactly ("my own TV indicator → my own API bot → my account") and get a yes;
(3) tune it to their risk limits (challenge balance, 1% risk, 1/day, max daily loss + drawdown;
start `MT5_MIN_GRADE=A+`). HFT risk is ~zero (1 trade/day; BE monitor only *modifies* SL, never opens new
trades). Context: 2-step challenge.

### 🏦 Funded / prop-account pre-flight (e.g. FundingTraders) — DO BEFORE connecting real funded money
1. **CHECK THEIR AUTOMATION RULES FIRST** — many prop firms ban bots/EAs/API/copy trading. If banned,
   connecting this risks the funded account being revoked even though execution is correct. Get it in
   writing from their support.
2. Set `ACCOUNT_BALANCE` to the funded size so 1% lot sizing is correct.
3. Align with their limits (daily cap, risk %, max drawdown); start `MT5_MIN_GRADE=A+` on funded money.
4. SL-always-attached already satisfies "stop required on every trade" rules.

### 🌍 Deployment model & 24/7 execution (IMPORTANT — common confusion)
**MetaAPI runs its OWN MT5 terminal in the cloud** (this is what "Deployed" + the ~$9/mo buys). The
user's local MT5 app is **NOT** in the trade path — it's only a viewing window.
- **Local run (Mac + ngrok):** dev/testing only. Bot at `localhost:8000`; ngrok tunnels a public URL to
  it for TradingView. ngrok URL changes each restart and dies when the Mac sleeps. Mac must stay on.
- **Railway run (production):** Railway gives a permanent public HTTPS URL — **no ngrok needed**. Point
  the 6 TradingView alerts (London+NY × EURUSD/XAUUSD/CHFJPY, condition "alert() function calls") at
  `https://<railway-app>.up.railway.app/webhook`.
- **Once on Railway, execution + the BE monitor run fully 24/7 in the cloud** — Mac OFF, MT5 app CLOSED,
  Wine not running: **trades still fire and breakeven still moves.** The user opens MT5 only to watch.
- **Caveat:** the bot already runs on Railway for the Telegram coach (same token → the local-vs-Railway
  `getUpdates` Conflict). Execution must live in **ONE** place. Plan: add the MetaAPI + `MT5_*`/`BE_*` env
  vars to Railway, run execution there, keep local for dev only (§5 item 2).

### ✅ What the bot CAN do
- Receive alerts from **any** indicator that posts the right JSON+secret to `/webhook` (London, NY, APEX,
  any future one) — all share the same pipeline.
- Auto-size lots from account balance and risk %.
- Filter by grade (`MT5_MIN_GRADE`) — **4-tier, synced with the indicator: A+ > A > B > C**
  (`signal_utils` preserves "A"; `mt5_executor.GRADE_ORDER = {A+:4,A:3,B:2,C:1}`; Telegram emoji A+/A 🟢,
  B 🟡, C 🔴). `min=B` → takes A+/A/B; `min=A` → A+/A; `min=A+` → A+ only.
- **Enforce a strict daily trade cap** (`MAX_TRADES_PER_DAY`, default 1) across ALL assets/sessions/
  indicators — once hit, every further signal that day is logged but NOT traded. Survives restarts
  (persisted), resets at CEST midnight.
- Auto-execute market orders with the Pine's exact entry/SL/TP on MT5 (via MetaAPI).
- **Auto-move SL to breakeven** at a configurable R (mirrors Pine `beThresholdR`).
- **Auto-close stale positions** after N hours (mirrors Pine `tradeExpiryHours`; `EXPIRY_HOURS`, 0=off).
- **Accept per-position management settings from the Pine webhook** (`be_trigger_r`/`expiry_hours`) so
  bot↔indicator settings stay in lockstep; `.env` defaults used when Pine doesn't send them.
- Post rich Telegram messages (signal + grade + execution result); act as the Claude mentor in chat.
- Work with **any MT4/MT5 broker** MetaAPI supports — switch by editing the MetaAPI account credentials
  or swapping `METAAPI_ACCOUNT_ID`.

### ❌ What the bot does NOT do (yet)
- **No trailing stop** (only the one-time BE move). Easy extension on the same monitor.
- **No partial take-profit / scale-out** (Pine sends a single TP).
- **No multi-account fan-out** — fires to ONE `METAAPI_ACCOUNT_ID`. (Designed extension: list of IDs.)
- **No outcome-webhook execution** — Pine's `trade_result` / `trade_expiry` JSON updates stats/Telegram
  but the bot does not itself close positions on those events (the broker SL/TP/BE handles exits).
- **No Telegram close commands yet** (`/close all`, `/positions`) — proposed in §5.
- **No pending/limit orders** — market execution only (Pine fires at entry on the engulf close).
- **No reconnect-and-resume of BE state across a full restart beyond what's inferable from live SL** (it
  re-derives from positions each boot; fine because SL≈entry ⇒ already-BE is detected).

---

## 5. NEXT TASK QUEUE  (do top-first; CONFIRM before editing — see §1)

> **▶ Exact-settings parity — PART 1 (bot side) ✅ SHIPPED & tested on demo.** Added the time-expiry
> monitor (mirrors Pine `tradeExpiryHours=24`) into the position monitor, plus per-position settings
> (`register_position_settings`) so the bot uses `be_trigger_r`/`expiry_hours` sent by Pine, falling back
> to `.env`. New keys `EXPIRY_ENABLED`/`EXPIRY_HOURS`.
> **▶ Exact-settings parity — PART 2 (Pine side) — STILL PENDING (needs explicit go + TradingView push):**
> add `"be_trigger_r": <beThresholdR>, "expiry_hours": <tradeExpiryHours>` to the London + NY alert JSON.
> Until then the bot uses `.env` defaults (already matched: 1.5R / 24h). Pine edits = indicator project
> (`docs/HANDOFF.md`, `wisemind-ai.mdc`); confirm + compile-clean before touching `.pine`.
> **Learning = CONFIRMED as analytics + Claude advice (NOT self-mutating ML); Michael approves rule changes.**

1. **Telegram close commands** — `/positions` (list open + P&L), `/close all`, `/close <SYMBOL>`,
   `/close half`. Uses `mt5_executor.get_positions()` + `close_position()` (+ a partial-close helper).
2. **Decide where execution permanently runs** — local (Mac + ngrok, only while Mac is on) vs Railway
   (24/7). Resolve the Telegram getUpdates conflict by running execution in ONE place. If Railway: add the
   MetaAPI env vars there and keep local for dev only.
3. **ngrok → TradingView wiring** — 6 alerts (London+NY × EURUSD/XAUUSD/CHFJPY) all pointing at
   `<ngrok>/webhook`, condition "alert() function calls". (Then flip `.env` to live to go fully automatic.)
4. **Trailing stop (optional)** — extend the BE monitor to trail SL by N×ATR or by R after BE.
5. **Multi-account fan-out (optional)** — `METAAPI_ACCOUNT_IDS=a,b,c`, loop execute on each (mini copy
   trader). Note MetaAPI bills per account.
6. **Fill `entry_price`** in `execute_trade` result by reading the position after open (cosmetic).
7. **Broker-suffix map** in `mt5_executor` for when Michael moves off IC Markets bare symbols.
8. **HQ execution-event forwarding** — bot POSTs `execution` / `be_moved` / `position_closed` events to
   `{WISEMIND_HQ_URL}/webhook`; HQ stores + SSE-broadcasts them so the dashboard documents real trades
   (not just signals). See §5B. ⚠️ HQ is live on Railway — confirm before editing it.

---

## 5A. ✅ PHASE 0 SAFETY — BUILT & TESTED (code done; deploy steps below)
Params: `ADMIN_USER_ID=5082485728`, `MAX_DAILY_LOSS_PCT=2`, `ERROR_ALERTS=true`,
`DAILY_STATE_PATH=/data/daily_trades.json` (needs Railway volume at /data). All steps DONE:
- [x] 1. `config.py` — ADMIN_USER_ID, MAX_DAILY_LOSS_PCT, ERROR_ALERTS
- [x] 2. `safety.py` (NEW) — `is_paused()/set_paused()`, `check_daily_loss()` (sticky day block),
      `loss_status()`; state in `bot_state.json` next to the daily file (volume-persisted)
- [x] 3. `mt5_executor.py` — `get_account_equity()`
- [x] 4. `webhook_handler.py` — gating order: paused → grade → (lock) daily-cap → daily-loss → execute;
      error-alert Telegram on failed order; Telegram lines for paused / loss-blocked
- [x] 5. `bot.py` — `/pause` `/resume` (admin-gated to ADMIN_USER_ID) + `/status` (anyone)
- [x] 6. `.env` — keys added (local)
- [x] 7. Tested: pause on/off ✅; daily loss blocks at exactly −2% and stays sticky ✅; `import bot` clean ✅
**REMAINING TO GO LIVE (deploy):** commit+push; on Railway bot service add vars `ADMIN_USER_ID=5082485728`,
`MAX_DAILY_LOSS_PCT=2`, `ERROR_ALERTS=true`, `DAILY_STATE_PATH=/data/daily_trades.json`, AND **add a Volume
mounted at `/data`** (Settings → Volumes) so state persists across redeploys. Then verify logs.
KNOWN LIMITATION (logged): daily-loss baseline = first equity the bot sees that day (lazy). Fine for demo;
before funded, refine to the broker's true day-start balance (server-midnight) for exact prop-firm DD.

## 5C. 🧠 PHASE 1 BRAIN — BUILD PROGRESS (resume here)
Volume `/data` created on Railway ✅. Build order: memory → briefings → tools.
- [x] **STEP 1 — Memory/Learning (DONE, tested, deployed):** `database.py` DB path now configurable
  (`DATABASE_PATH` env → set `/data/trades.db` on Railway so history persists on the volume). New
  `stats.py` (`compute_stats` reads `trade_results`; win rate, expectancy R/trade, total R, by
  session/symbol, recent streak; `format_stats`, `build_review_prompt`). `bot.py` commands **`/stats`**
  (numbers) + **`/review`** (Claude analyses history → data-backed recommendations, advisory only).
  Tested locally (1 result → 100% WR, 5R). ⚠️ MUST set Railway var `DATABASE_PATH=/data/trades.db`.
- [x] **STEP 2 — Daily briefings (DONE, deployed):** `briefings.py` self-pacing asyncio scheduler started
  in `bot.py` boot; morning 08:30 / evening 17:30 CEST (`BRIEF_MORNING`/`BRIEF_EVENING`, `BRIEFINGS_ENABLED`);
  Claude writes from real stats only. `/brief` fires one on demand. Tested (next-fire timing correct).
- [x] **STEP 3 — Tool agency (DONE, tested live, deployed):** `agent_tools.py` read-only Claude tool-use
  loop (`get_open_positions`, `get_account`, `get_stats`). `bot.py` **`/ask <q>`** (agent looks + answers —
  tested live: fetched real balance/equity/positions) and **`/close [SYMBOL|all]`** (admin-gated = Michael's
  approval). Write actions are NOT given to the LLM — only Michael's explicit commands execute them, per his
  rule. `mt5_executor.py` added get_account_info/get_open_positions/close_position_by_id.
**🧠 PHASE 1 BRAIN COMPLETE** (memory + briefings + tool agency). Commands now: /pause /resume /status
/stats /review /brief /ask /close. **Railway vars still to add for full effect:** `DATABASE_PATH=/data/
trades.db`, `DAILY_STATE_PATH=/data/daily_trades.json` (+ Phase 0: ADMIN_USER_ID, MAX_DAILY_LOSS_PCT,
ERROR_ALERTS). Briefings default ON. **Next unbuilt: Phase 2 execution polish (trailing/partial TP, news
blackout) + HQ execution merge.**

## 5B. WISEMIND HQ INTEGRATION + PRODUCT / SELLABILITY ROADMAP (vision — keep current)

### WiseMind HQ — how it connects today
- **HQ** = `wisemind-hq/server.js` (Node.js, on Railway, live at
  `wisemind-hq-production.up.railway.app`). Has its **own** `/webhook`, an `evaluateSignal()` +
  `calculateLotSize()` ported from the bot, SQLite (`signals`, `trade_results`, `users` tables), **SSE
  live feed** to the dashboard, and **user accounts** (student register/login + admin code) — i.e. the
  multi-tenant SaaS foundation already exists.
- **Current bot→HQ link:** `webhook_handler.py` forwards the raw signal `data` to `{WISEMIND_HQ_URL}/webhook`
  on each alert (and forwards `trade_result` events too). So **HQ already documents the SIGNAL** and shows
  it live on the dashboard.
- **The gap:** HQ does NOT yet receive the bot's **EXECUTION truth** — whether MetaAPI actually filled it,
  the fill price, lot, grade, skipped/failed, BE-moved, or broker-side close P&L. HQ shows "a signal came
  in," not "the bot really opened 2.0 lots @ X and moved to BE."

### Planned: "merge the bot into HQ" (execution-event forwarding) — see §5 item 8
- Bot POSTs execution events to HQ: `{event:"execution", status:"executed|skipped|failed", order_id,
  fill_price, lot, grade, symbol, side, sl, tp, session, ts}`; also `event:"be_moved"` and broker-side
  `event:"position_closed"` with realized P&L.
- HQ: accept these event types in `handleWebhook`, store (extend `trade_results` or a new `executions`
  table), broadcast via existing SSE so the dashboard shows live execution + BE + close. ⚠️ HQ is LIVE on
  Railway — confirm before editing it.
- End state: one dashboard shows **signal → execution → breakeven → close**, per user, in real time.

### 🚦 ROLLOUT PLAN (Michael's chosen path — demo-on-Railway first, then funded)
- **Stage 1 — Railway + DEMO for ~1 week:** deploy the bot to Railway (24/7), add MetaAPI + `MT5_*`/`BE_*`/
  `EXPIRY_*`/`MAX_TRADES_PER_DAY` env vars there, **enable execution on the IC Markets demo**, point the 6
  TradingView alerts (London+NY × EURUSD/XAUUSD/CHFJPY) at the Railway `/webhook`, and let it run with the
  Mac off. Keep `ACCOUNT_BALANCE=100000` (matches demo) so lot sizing is accurate during the test.
  Goal: validate signals→trades→BE→expiry→daily-cap over a full week, cloud-side.
- **Stage 2 — switch to FundingTraders $50k funded (only after a clean week + written go from their
  support):** in MetaAPI, edit the same account's creds → funded login/password/server (same Account ID →
  no code change). Change env: **`ACCOUNT_BALANCE=50000`**, **`MT5_MIN_GRADE=A+`** (best signals only),
  keep `MAX_TRADES_PER_DAY=1`. Put `DAILY_STATE_PATH` on the Railway persistent volume so the daily cap
  survives redeploys. Re-verify against FundingTraders' max daily-loss + drawdown rules.
- Resolve the Telegram getUpdates conflict by running execution **only on Railway** (local = dev) once
  Stage 1 starts.

### 🧠 "Thinking agent" vision (Michael wants the bot to be its own intelligent agent)
The bot ALREADY has a brain (Claude Haiku/Sonnet powering the Telegram coach). To make it a true
*thinking agent* (not hype), add 4 layers — all advisory/analytical, never overriding the deterministic
strategy:
- **(A) Reasoning-per-trade.** On each signal, Claude analyses it + live context (open positions, today's
  P&L, recent results, optional news/calendar) and posts a verdict + explanation to Telegram/HQ ("A+ London
  T2 after clean Asia sweep, HTF aligned — high confidence"). Post-trade debrief too. Can FLAG, and with
  DETERMINISTIC guardrails optionally gate, but never invents prices or moves SL/TP.
- **(B) Memory + learning** (= the confirmed analytics loop): persist every trade with full context →
  running stats → Claude reasons over history → evolving recommendations Michael approves.
- **(C) Tools / agency** (tool-calling): give Claude functions — get_positions, get_stats, get_news,
  get_account, close_position (approval-gated) — so it can answer "how am I doing today?", "worried about
  this trade?", and take *approved* actions.
- **(D) Proactive briefings**: morning pre-session brief (news, Asia range, bias) + evening debrief.
GUARDRAILS (hard): LLM ADVISES, deterministic rules EXECUTE; the edge is the Pine strategy, not the LLM;
never let it override entry/SL/TP or invent data; Michael approves any rule change; no self-mutating ML.
**Michael wants: daily briefings + memory/learning loop + tool agency (and the full improvement plan).**
**Phase 1 CONFIRMED params (build order: memory → briefings → tools; build only after volume is set up):**
- Daily briefings: **08:30 morning / 17:30 evening CEST** (before London / after NY).
- Tool agency: read-only (positions/stats/account) is automatic; **EVERY write/action the agent wants to
  take requires Michael's explicit approval before it executes** (close, pause, any change). Approval-gated.
- Memory/learning DB + trade journal must live on the **/data volume** (persist across redeploys) — so the
  Railway volume setup is the prerequisite and must be done first.

### 📚 FULL IMPROVEMENT CATALOG (everything that would make the bot better — Michael asked for all of it)
1. **Safety/governance (DO BEFORE FUNDED):** Telegram kill-switch `/pause` `/resume`; error alerting
   (ping Michael if an execution fails); **daily loss limit** (stop trading at −X% day) + **max drawdown
   guard**; persistent state volume (`/data`) so the daily cap survives redeploys; signal idempotency /
   dedup (don't double-execute a retried/duplicate webhook); heartbeat ("bot alive") ping.
2. **Intelligence (the agent):** reasoning-per-trade + post-trade debrief; daily briefings; memory+learning
   loop (journal→stats→advice); tool agency (Claude functions: positions/stats/news/account/close-with-
   approval); `/positions` `/close` Telegram commands.
3. **Execution polish:** trailing stop (after BE); partial TP / scale-out (e.g. 50% at 2R, runner to TP);
   spread guard + slippage guard (skip if market moved too far from Pine entry); news-blackout window.
4. **Risk:** equity-based lot sizing (size off live equity, not fixed balance); per-session caps.
5. **Observability:** HQ execution-event merge (signal→exec→BE→close live on dashboard); equity curve +
   WR by grade/session/asset; log EVERY signal (even non-traded) for analysis.
6. **Scale/product:** multi-account fan-out; multi-tenant SaaS (per-user broker + billing); indicator
   licensing; 2-year stats site.
RECOMMENDED ORDER (Michael's stage = demo week → $50k funded): **Phase 0 safety essentials first**
(kill-switch, error alerts, daily-loss limit, /data volume) BEFORE funded; then the intelligence layers;
then execution polish; then HQ merge + scale.
**CONFIRMED by Michael — Phase 0 = NEXT BUILD (build order locked):**
- Kill switch `/pause` `/resume` `/status` — **gated to Michael's Telegram user ID only** (`ADMIN_USER_ID`).
- Error alerting on failed execution / MetaAPI disconnect (`ERROR_ALERTS=true`).
- **Daily loss limit = 2%** (`MAX_DAILY_LOSS_PCT=2`; tracks day-start equity vs current; auto-stop for the
  day when breached).
- Persistent state on Railway `/data` volume (`DAILY_STATE_PATH=/data/daily_trades.json` + pause/equity
  state) so redeploys can't reset the cap or un-pause.
- STANDING RULE reinforced: **always confirm with Michael before building** (see §1).
- BLOCKER: need Michael's numeric **Telegram user ID** (via @userinfobot) for the admin gate, then go.

### 💡 Live setup play-by-play (Michael's idea — confirm before build)
Michael wants real-time updates as a setup FORMS: "Asia sweep occurred", "displacement confirmed",
"price tapped PD zone", "engulf forming — trade about to fire", "criterion X hit". HOW it works (honest):
the deployed bot/Claude CANNOT browse TradingView live — it only knows what the Pine indicator SENDS it.
So this needs **intermediate `alert()` calls added in the Pine indicator** at each stage (sweep / displace /
PD touch / engulf-forming / fired / invalidated) → bot receives them on /webhook as "stage" events →
posts to Telegram, optionally narrated by Claude → live play-by-play. REQUIRES: (1) Pine edits = indicator
project (`docs/HANDOFF.md`, confirm + TradingView push); (2) watch TradingView alert-slot limits (Pro=20,
Premium=400) — stage alerts × assets add up; (3) bot: handle a `stage`/`event` field in the webhook +
format/narrate. Great for engagement + (in SaaS) broadcast to all users. Status: idea logged, awaiting go.
NOTE: live `/status` + `/brief` verified working on Railway 2026-06-02 (brief rendered in English). Minor:
`/help` command listing all commands not built yet (Michael tried /commands).

### Proposed directions (discussed, awaiting Michael's go — do NOT build yet)
- **Learning feedback loop (RECOMMENDED form of "make it learn").** Record every executed trade with full
  context (setup, grade, session, asset, planned/achieved R, BE-hit, win/loss) → compute running stats
  (win rate by grade/session/asset/setup, expectancy, BE-then-TP rate) → **Claude analyzes and gives
  data-backed recommendations** ("NY shorts 38% over 21 trades → A+ only"). Michael stays in control of
  any rule change. Uses existing Claude + DB + HQ. **NOT** self-mutating ML: with hundreds (not millions)
  of trades a black-box model overfits and can destroy the edge — the edge is the Pine strategy; ML
  *advises*, never *auto-decides*.
- **Exact-settings parity bot↔indicator.** Entry/filter settings live in Pine (bot just executes whatever
  fires — already exact). MANAGEMENT settings mirrored in the bot since the broker runs the live position:
  BE@1.5R ✅; **24h auto-close ✅ (Part 1 shipped — expiry monitor mirrors `tradeExpiryHours`)**; trailing
  = neither (matched). Bot already **reads `be_trigger_r`/`expiry_hours` from the webhook** when present.
  **Remaining (Part 2):** make Pine actually SEND those two values in the London+NY alert JSON so they can
  never drift — separate indicator-project edit, needs go + TradingView push.

### 🧩 SaaS GAP ANALYSIS — what's MISSING to serve hundreds of users (Michael asked "what's missing")
Today = SINGLE-tenant: ONE bot, ONE MetaAPI account, GLOBAL env-var settings, ONE Telegram chat, admin-only
dashboard, SQLite, signals from Michael's own TradingView. To sell to hundreds, the missing layers:
1. **Signal fan-out rearchitecture (the core change).** Signals come CENTRALLY from Michael's indicators →
   ONE webhook → **fan out to every subscribed user's account**, each sized + filtered by THEIR settings.
   Users do NOT set up their own TradingView. Needs an async fan-out engine + per-user execution + rate-limit
   handling for many MetaAPI accounts.
2. **Per-user broker connect.** Each user connects THEIR MT5 (login/pwd/server) → HQ provisions a MetaAPI
   account for them via MetaAPI provisioning API. (Currently one global METAAPI_TOKEN/ACCOUNT_ID.)
3. **Per-user settings in DB** (not env vars): risk%, assets, min-grade, BE, expiry, daily cap, daily loss,
   pause — each editable by the user from their dashboard.
4. **Per-user state + isolation:** daily cap / pause / loss-limit / journal / stats all per-user in the DB;
   user A never sees/touches user B. (Currently global JSON files.)
5. **Personalized dashboard (Michael's explicit ask).** Every member logs in and sees ONLY their own
   equity, trades, stats, journal, and can edit ALL their settings + connect their broker themselves.
   Admin (Michael) sees aggregate/all. Onboarding flow: signup → connect broker → set prefs → go live.
6. **Billing (Stripe):** subscriptions/plans/trial/cancel; gate execution to paying users; pricing must
   cover ~$9/mo per MetaAPI account.
7. **Bilingual AI coach (Michael's ask):** English-primary system prompt that **speaks both Swedish and
   English** (detect user language, reply in kind); per-user coach memory + per-user stats context.
8. **Postgres (not SQLite):** hundreds of users with concurrent writes need a real DB; move HQ + bot off
   SQLite to Postgres (Railway Postgres plugin).
9. **Per-user reliability:** one user's broker error must not affect others; connection pooling for many
   MetaAPI accounts; per-user error alerts.
10. **Security/compliance:** encrypt stored broker creds; password reset + 2FA; **GDPR** (EU/Swedish users),
    ToS, risk disclaimers, privacy policy; regulatory/licensing review for selling automated trading.
11. **Admin tooling:** all-users view, per-user + global kill switch, subscription mgmt, support, broadcasts.
12. **Indicator licensing:** TradingView invite-only access tied to subscription status.
GAP SUMMARY: the engine (execution, BE, expiry, grades, safety, brain) is BUILT for one account; the
missing ~80% of the *product* is the **multi-tenant layer**: fan-out, per-user broker+settings+state+
dashboard, billing, Postgres, bilingual coach, security/legal. Recommended order: Postgres → per-user
auth/settings/dashboard → per-user broker connect → signal fan-out → bilingual coach → billing → legal.

### Product / Sellability roadmap (the "sell the bot + indicator" vision)
Aligns with Michael's existing **500-student release gameplan** (see memory + WiseMindBrain MASTER).
```
 Phase 1 ✅ Single-user execution bot works (MetaAPI, BE monitor) — DONE this session.
 Phase 2  Harden YOUR bot: trailing stop, partial TP, daily loss limits / max-trades, prop-firm guards,
          Telegram /close+/positions, full execution logging, fill-price capture.
 Phase 3  Multi-account fan-out (you run several accounts): METAAPI_ACCOUNT_IDS=a,b,c, loop execute.
 Phase 4  Multi-tenant SaaS: HQ already has user accounts — add per-user broker connect (each user's own
          MetaAPI account/creds), per-user settings (risk%, assets, min-grade, BE), isolation, billing
          (Stripe), per-user execution dashboard.
 Phase 5  Sell: indicator licensing (TradingView invite-only scripts + access mgmt) + bot subscription;
          disclaimers, risk warnings, ToS.
```
**DISTRIBUTION MODELS (how to actually sell it — "downloadable app" is NOT the right model for a
server/API bot):**
1. **SaaS multi-tenant (RECOMMENDED — already ~80% there).** Michael hosts ONE bot; customers sign up on
   WiseMind HQ (HQ already has user accounts/auth!), connect THEIR OWN broker (their MetaAPI account),
   set their risk, pay a subscription (Stripe). They download nothing — just log in. Needs: per-user
   broker connect + per-user settings + isolation + billing + licensing.
2. **Self-host package (the literal "downloadable").** Sell the repo/Docker + a Railway one-click; buyer
   runs it on their own Railway + their own MetaAPI. Lower hosting burden on Michael but HIGH setup-support
   burden + code-piracy risk. Suits technical buyers only.
3. **Copy-trading / managed.** One master account; customers connect their account and MIRROR Michael's
   trades (MetaAPI CopyFactory). They run nothing.
4. **Indicator-only license + DIY guide.** Sell the TradingView invite-only indicator + a setup template.
Constraints: MetaAPI bills ~$9/mo PER account (pricing/architecture decision at scale); regulation/
licensing exposure (esp. managed/copy); disclaimers + ToS required; support load. Recommended path: SaaS
(model 1) since HQ user-accounts already exist.
```
**MetaAPI account-edit settings (verified on the demo, all left at defaults — nothing needs changing):**
account `bd1c91cb…`, login 52879989, server `ICMarketsEU-Demo` (valid ✓), magic 0, max slippage 30,
quote interval 2.5s, resource slots 1, dedicated IPv4 off. Leave the MT-password field **blank** when
editing (blank = keep current). **"Place manual trades" (G2-only)** makes API trades look *manual* to the
broker — irrelevant on the demo (leave OFF); potentially relevant if a **prop-firm** account is connected
later, BUT using it to evade a prop firm's automation ban is still a terms violation — only use where
automation is genuinely allowed.

**Honest constraints to design around (not blockers):** financial-regulation/licensing exposure when
selling automated trading/signals (customers trading their OWN accounts via the software is lighter, but
needs disclaimers + legal review); MetaAPI bills ~$9/mo PER account (pricing/architecture decision at
scale); liability/refunds/reputation if it loses money; many prop firms ban automation (affects who can
use it). "Train the bot" (ML) is a separate large project — the edge is the Pine strategy + analytics, not
a black-box model; keep ML for *analysis/coaching* (Claude), not trade decisions, unless deliberately
scoped later.

---

## 6. Handoff protocol (the "automatic middle brain")
**This is obligatory and proactive — Michael should not have to ask (see §1 "DOCUMENT EVERYTHING").**
When you finish a slice, **before ending the session**:
1. Move the shipped item into **§3 Current status** with file/function/param-level detail + how it was
   verified (e.g. "tested on demo, position #… opened/closed").
2. Re-order **§5 Next task queue** so the top item is the true next thing.
3. If you changed the lifecycle or capabilities, update **§4** (incl. the CAN/CANNOT lists).
4. Record any **future/roadmap/vision** discussion (short-term, long-term, "maybe later", product/sell
   ideas) in **§5 / §5B** — even half-formed ideas. Nothing about direction stays only in chat.
5. Note any new `.env` keys in §3 and add them to the `.env` with safe defaults.
6. Leave `.env` in **safe state** (`MT5_EXECUTION_ENABLED=false`, `MT5_DRY_RUN=true`) and the demo
   account **flat** (no leftover test positions) unless Michael asked otherwise.

That's the contract: whoever picks up next (Claude Code OR Cursor) reads §0→§5 and is instantly oriented.
**The file is the shared brain.**

---

## 7. 📋 PASTE-READY RESUME PROMPT (copy into a fresh Cursor / Claude chat)
```
Read wisemind-ai/docs/BOT_HANDOFF.md and ~/AI Coding/CLAUDE.md first, then continue the WiseMind
EXECUTION BOT work. Obey BOT_HANDOFF §1 hard rules: CONFIRM before changes ("this is my life work, be
precise"); never auto-trade without an explicit go (default .env stays MT5_EXECUTION_ENABLED=false +
MT5_DRY_RUN=true); demo first; secrets via .env only; Pine is the brain, the bot executes its exact
entry/SL/TP. Run/verify per §2 (start bot, curl a test signal, prove execution on demo, close positions).
Pick the top item from §5, propose the plan, build only after a yes. When done, update §3/§4/§5 per §6 and
leave .env safe + the demo flat.
```
