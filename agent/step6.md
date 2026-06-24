# Step 6 — Production polish (runs unattended)

**Goal:** the small correctness/ops details that separate "works on my laptop"
from "runs unattended." Four pieces: a **market-open gate** so strategies only
act when the market is open, a **clean teardown** on stop, **Discord alerting**
from the watchdog so a wedged strategy pages you, and **supervision** (systemd /
Docker) with a restart policy that leans on Step 3's record-then-submit so
restarts are safe.

## Files touched

| File | Change |
|------|--------|
| `services/alpaca_trader.py` | New thin `is_market_open()` (wraps Alpaca's clock, fail-closed) |
| `strategies/base.py` | Market-open gate around `loop_once()`; teardown + final `stopped` beat on stop |
| `strategies/heartbeat.py` | `requires_market_open = False` (test probe ticks 24/7) |
| `engine.py` | Watchdog now **pages Discord** on a wedge (once per wedge, re-arms on recovery) |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml` | Containerized run with `restart: unless-stopped` |
| `deploy/trading-engine.service` | systemd unit with `Restart=always` (bare-metal alternative) |

## What changed

### Market-open gate

- **`AlpacaTrader.is_market_open()`** — one call to `get_clock().is_open`.
  **Fail-closed**: if the clock call errors, it returns `False`, so a broker or
  network blip never lets a strategy trade blind. Matches the print-on-error
  style of the rest of the trader.
- **`strategies/base.py`** — new class attr `requires_market_open = True`. The
  `run()` loop checks it at the top of each iteration: when the market is
  closed it **skips `loop_once()` but stays alive** — beats `status="market_closed"`
  (or the watchdog would flag it wedged) and sleeps `poll_interval`, then
  re-checks. No orders fire outside market hours.
- **`strategies/heartbeat.py`** — overrides `requires_market_open = False`. It's
  a pure liveness probe with no orders, so it should keep ticking overnight and
  on weekends to stay useful for verifying the threading model.

> Note: the gate is a network call per tick. With the real `poll_interval`
> (300s) that's trivial; the throwaway 5s `rsi_buy` interval in settings is a
> dev value to revert. Caching the clock was deliberately skipped to keep the
> method thin.

### Teardown on stop

- The `teardown()` hook already existed and is called when `run()`'s loop exits.
  Step 6 hardens the stop path: teardown is now **wrapped in try/except** so a
  failing cleanup can't skip what follows, and the strategy beats one final
  `status="stopped"` row. The health view then reads a *deliberate* exit instead
  of a row aging into a false "wedged" (the watchdog only inspects live threads,
  so a stopped strategy is never paged — this just keeps the status honest).

### Alerting — watchdog pages Discord

- `engine.py` imports `send_discord_message` and keeps a `self._wedged_alerted`
  set. In `_check_heartbeats()`, a WEDGED strategy now calls **`_alert_wedged()`**
  in addition to logging.
- **Paged once per wedge, not per scan**: the name is added to `_wedged_alerted`
  on the first page and skipped while it stays wedged. When the strategy beats
  fresh again (age ≤ stale), the name is `discard`-ed, so a later *re-wedge*
  pages anew.
- `send_discord_message` is already fail-soft (missing URL = no-op, errors only
  log), so a webhook hiccup can't take down the watchdog scan. Wire it by
  setting `DISCORD_WEBHOOK_URL` in `.env` — the same webhook Step 3 uses for
  order notifications.

### Supervision — systemd / Docker

- **`docker-compose.yml`** runs the engine with `restart: unless-stopped`
  (relaunch on crash or host reboot, but honor a deliberate `stop`) and a 30s
  `stop_grace_period` so `engine.shutdown()` can signal and join its threads on
  SIGTERM. Secrets come from `.env` via `env_file`. `Dockerfile` is a slim
  Python 3.10 image, deps cached in their own layer, `PYTHONUNBUFFERED=1` so
  logs stream to `docker logs`. `.dockerignore` keeps `.env`/`.git`/venv out of
  the build context and image.
- **`deploy/trading-engine.service`** is the bare-metal equivalent:
  `Restart=always`, `RestartSec=5`, `EnvironmentFile=/opt/lol/.env`,
  `TimeoutStopSec=30` for the graceful shutdown. Header comments cover install
  (`systemctl enable --now`) and which paths to edit.

**Why restarts are safe** (the Step 3 claim, made concrete): on relaunch the job
scheduler resumes its cadence from `job_runs` (Step 5) rather than re-firing
everything, and every order carries a unique `client_order_id`
(`strategy__symbol__rand`) that **the broker dedupes** — Alpaca rejects a second
order with the same id. So an order in flight when the process dies can't
double-submit on replay.

> Caveat worth flagging: the DB side of record-then-submit (`_record`/`_mark`
> and `insert_row`/`update_row`) is currently **commented out** in
> `order_gateway.py` / `supabase.py`. The *broker* idempotency above already
> prevents a double-submit, so restart safety holds; but until those are
> re-enabled there's no durable `trades` row to reconcile against after a crash.
> Re-enable them (and create the `trades` table) for full audit/recovery.

## Verifying

- **Market-open gate**: with the market closed, start the engine. `rsi_buy`
  logs nothing from `loop_once` but its heartbeat keeps refreshing with
  `status="market_closed"`; `heartbeat` keeps ticking. Reopen (or temporarily
  stub `is_market_open()` to `True`) and `loop_once` resumes.
- **Teardown / clean stop**: Ctrl-C. Each strategy runs `teardown()`, writes a
  final `status="stopped"` heartbeat, logs `stopped`, and the watchdog +
  scheduler join — no lingering threads.
- **Alerting**: wedge a strategy (`time.sleep(9999)` in its `loop_once`) with
  `DISCORD_WEBHOOK_URL` set and a low `HEARTBEAT_STALE_SECONDS`. Within one
  watchdog scan you get **one** Discord page (not one per scan). Heal it and the
  alert re-arms.
- **Supervision + restart safety** (the headline test): run under
  `docker compose up -d` (or systemd). `kill -9` the process mid-run. The
  supervisor relaunches it; the scheduler reads `job_runs` and does **not**
  re-fire a job that already ran this interval; any order whose
  `client_order_id` already reached Alpaca is rejected as a duplicate, so
  **nothing replays twice**. It resumes clean.

## Notes for later steps

- The market-open gate trades blind-safety for a `get_clock()` call per tick; if
  tick rates climb, cache the clock for a few seconds in the trader.
- Re-enabling record-then-submit (uncomment `_record`/`_mark` +
  `insert_row`/`update_row`, create the `trades` table) closes the audit/recovery
  gap and gives the admin API a real order ledger to read.
- The watchdog now both observes *and* pages. A further step could make it
  **act** — auto-restart the wedged strategy via `stop_strategy`/`start_strategy`,
  or trip the engine-level pause.
