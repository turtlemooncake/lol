# Step 0 — Finish the strategy contract (one strategy, one thread)

**Goal:** a single strategy runs forever on its own thread and stops cleanly on Ctrl-C.

This step locks the subclass contract (`setup` / `loop_once` / `teardown`) that every later
step hangs off. Nothing downstream changes it.

## Files touched

| File | Change |
|------|--------|
| `strategies/base.py` | Finish the `Strategy` base class: lifecycle + interruptible loop |
| `strategies/rsi_buy.py` | Concrete strategy implementing `loop_once()` (just logs `tick` for now) |
| `strategies/__init__.py` | `REGISTRY` mapping strategy name → class |
| `main.py` | Build `Context` once, start one strategy on a thread, wait for shutdown |

## What changed

### `strategies/base.py`
- Defines the **subclass contract**: `setup()` (one-time warmup, optional),
  `loop_once()` (abstract — one iteration), `teardown()` (cleanup, optional).
- Owns the **runner** `run()`: `setup()` → `while not stopped: loop_once() + sleep`,
  with per-iteration `try/except` so one bad cycle backs off instead of killing the thread.
- Replaces the old `self.running` bool with a `threading.Event` (`self._stop`).
  `self._stop.wait(seconds)` is an **interruptible sleep** — `stop()` wakes it instantly,
  so Ctrl-C never waits out a 300s poll and there's no 1s busy-wait.

### `strategies/rsi_buy.py`
- `RsiBuy(Strategy)` with `name = "rsi_buy"` and `loop_once()` that logs `tick`.
- No orders yet — order routing arrives in Step 3 (OrderGateway).

### `strategies/__init__.py`
- `REGISTRY = {RsiBuy.name: RsiBuy}` — the single place that maps a config key to a class.

### `main.py`
- `build_context()` constructs the shared services (`SupabaseDB`, `AlpacaData`, `AlpacaTrader`).
- Instantiates one strategy via `REGISTRY`, runs it on a daemon thread.
- Main thread blocks on a `threading.Event` until `SIGINT`/`SIGTERM`, then `stop()` + `join()`.

## Verifying

```bash
python main.py
```

- `poll_interval` for `rsi_buy` is temporarily set to **5s** in `config/service_settings.py`
  so you can watch it tick (revert to 300s later).
- `build_context()` constructs the real Supabase/Alpaca clients, so it needs `.env` keys
  present — even though `loop_once()` doesn't use `ctx` yet. Stub `ctx = None` if that's
  inconvenient for a pure tick test.
- Expected: a `tick` line per interval; a single Ctrl-C prints `shutting down...` →
  `stopped` within ~1s.

## Notes for later steps

- `main.py` hard-codes the one strategy by name on purpose — this is scaffolding.
  **Step 1** replaces that block with a loop over `STRATEGIES`; **Step 2** moves it into
  an `Engine`. Don't generalize `main.py` here.
