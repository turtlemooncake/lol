# Step 8 — Cloud-hosting readiness: dependency fix, ledger-based open time, shared parser

**Goal:** get the Step 1–7 engine ready to build and run as a container in the
cloud. The headline was a **broken `requirements.txt`** that would have let the
image build but crash on boot. Alongside that: retire the broker-order-history
reconstruction of a position's open time in favor of our now-durable `trades`
ledger, extract the duplicated Supabase-timestamp parser into `util`, and tidy
`download_candle_bars` (dead pagination loop) plus the Docker build context.

## Files touched

| File                         | Change                                                                                                                           |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `requirements.txt`           | **Critical fix.** Added the missing `supabase` tree; corrected a `websockets` pin conflict. Regenerated from the known-good venv |
| `util/__init__.py`           | **New** `parse_ts()` — shared Supabase timestamptz → aware-UTC parser                                                            |
| `engine.py`                  | Import `parse_ts` from `util` (removed its private `_parse_ts` copy)                                                             |
| `services/supabase.py`       | **New** `last_entry_time(symbol)` — latest submitted buy's `submitted_at` from `trades`                                          |
| `strategies/exit_monitor.py` | Time-stop now reads `parse_ts(ctx.db.last_entry_time(symbol))`                                                                   |
| `services/alpaca_trader.py`  | **Removed** `get_position_open_time()` and its now-unused `datetime` / `Sort` imports                                            |
| `services/alpaca_data.py`    | `download_candle_bars`: dropped the dead `while True` / `page_token` loop — one call per batch                                   |
| `.dockerignore`              | Also exclude `.DS_Store` and `sql/` from the build context                                                                       |

## What changed

### requirements.txt — the deployment blocker (fixed)

Two issues, either of which sinks a cloud deploy:

- **`supabase` and its entire dependency tree were missing.** `services/supabase.py`
  does `from supabase import create_client`, but the package (plus `postgrest`,
  `realtime`, `storage3`, `supabase-auth`, `supabase-functions`, `httpx`,
  `yarl`, …) was nowhere in the file. The image **builds fine then crashes on
  first boot** with `ModuleNotFoundError: No module named 'supabase'`. The local
  venv has it (which is why it ran locally), but the venv is `.dockerignore`d, so
  the container never saw it.
- **A pin conflict that fails `pip install` outright.** The old file pinned
  `websockets==16.0`, but supabase's `realtime` requires `websockets>=11,<16`.
  So even just adding `supabase` to the old list errors during resolution. The
  working venv actually has `websockets==15.0.1`.

Fix: regenerated `requirements.txt` from the known-good venv (`pip check` clean,
app runs) so it carries the full, internally-consistent set. Going forward, treat
the venv as source of truth (`pip freeze`) so it can't silently drift again.

### Position open time — from broker history to the `trades` ledger

Step 7 left a note: now that `trades` is live, read the opening fill from our own
ledger instead of reconstructing it from broker order history. Done here.

- **`SupabaseDB.last_entry_time(symbol)`** — the most recent `submitted` **buy**
  row's `submitted_at` for the symbol, `ORDER BY submitted_at DESC LIMIT 1`. With
  the one-position-per-name guard (we only buy a name while flat), the latest
  submitted buy _is_ the current position's entry. Returns `None` (→ time-stop
  skipped, take-profit still applies) when there's no recorded entry — e.g. a
  position opened before the ledger existed. Fail-soft (`None` on DB error).
- **`ExitMonitor._exit_reason`** now ages from `parse_ts(ctx.db.last_entry_time(...))`
  instead of `alpacaTrader.get_position_open_time(...)`.
- **`AlpacaTrader.get_position_open_time` deleted**, along with the now-unused
  `datetime` and `Sort` imports.
- **Behavioral note:** the ledger records **submission** time (`submitted_at`),
  not fill time. For a 10-day time-stop the difference is negligible, and it's
  more robust than the old order-history walk — but it is "time since we sent the
  buy," not "time since it filled."

### Shared timestamp parser

`engine.py` had a private `_parse_ts` for Supabase timestamptz strings; the new
exit-monitor path needs the same logic. Rather than duplicate (importing from
`engine` would be circular — `engine` imports `strategies`), it moved to
**`util.parse_ts`**. `engine.py` now imports it as `_parse_ts`, so its call sites
are unchanged.

### download_candle_bars — dead pagination loop removed

The old `while True` looped on a `page_token` that was always reset to `None`,
so it broke on the first pass anyway — the alpaca SDK paginates internally and
returns every bar in `bars.df`. Removing the naive `while` and just leaving the
break in made the loop hang (it re-fetched forever), so the fix is a **single
call per batch**, with a per-batch `except` that skips a bad batch instead of
sinking the whole download.

### Docker build context

`.dockerignore` now also drops `.DS_Store` and `sql/` (DDL applied to Supabase
out-of-band, not needed at runtime), keeping the image lean.

## Dockerfile / compose — reviewed, ship-ready

The Dockerfile is correct and unchanged: layer-cached deps, `PYTHONUNBUFFERED=1`
(so container logs aren't block-buffered), secrets via env (never baked), `slim`
base. Optional hardening noted for later: run as a non-root `USER`, pin the base
image by digest. `restart: unless-stopped` + the idempotent `client_order_id`
make restarts replay-safe.

- **Build & run:** `docker compose up -d --build`, then `docker compose logs -f`.
  The real test of the requirements fix is a clean boot — a missing `supabase`
  would crash-loop here (watch logs, not just `ps`, since `unless-stopped`
  relaunches silently). `docker compose ps` should read `running`, not
  `restarting`. UPDATE: this works

## Verifying

- **Time-stop via ledger:** a held name whose latest submitted buy in `trades` is
  ≥ 10 days old closes on the next exit tick tagged `time-stop`. A held name with
  no `trades` entry skips the time-stop (take-profit still fires).
- **No regressions in the watchdog/scheduler:** they still parse heartbeat /
  job-run timestamps via the relocated `util.parse_ts`.

## Notes for later steps

- **Local logging gotcha (not a bug):** when running a job directly (e.g.
  `buy_universe.py`) with stdout redirected to a file, Python block-buffers
  stdout, so prints don't appear until the process exits — looks like a hang.
  Run with `python -u` / `PYTHONUNBUFFERED=1` locally; the container already sets
  it. `buy_universe.py` also fetches the **full** filtered universe (thousands of
  symbols → hundreds of batches), so it's legitimately minutes long.
- **No request timeout** on `StockHistoricalDataClient`; a stalled batch can block
  the download indefinitely. Worth adding a timeout before this runs unattended.
- **`MAX_DAILY_LOSS`** is configured but still not enforced anywhere.
- Leftover unused `self._lock` fields in `AlpacaTrader` / `AlpacaData` /
  `SupabaseDB` — the gateway lock subsumes them; safe to delete.
