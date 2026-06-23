# Step 2 — Extract the Engine orchestrator

**Goal:** move start/join orchestration out of `main.py` into an `Engine` so
strategies can be started and stopped *individually* — the hook the admin API will
need later.

## Files touched

| File | Change |
|------|--------|
| `engine.py` | New. `Engine(ctx)` owns `strategies` + `threads` dicts and exposes `start()`, `shutdown()`, `start_strategy(name)`, `stop_strategy(name)`, `status()` |
| `main.py` | Shrunk to: wire services → `Context` → `Engine(ctx)` → `engine.start()` → wait on signal → `engine.shutdown()` |

## What changed

### `engine.py`
- `Engine.__init__(ctx)` holds `self.strategies: dict[str, Strategy]` and
  `self.threads: dict[str, threading.Thread]`, keyed by strategy name.
- `start()` loops `ServiceSettings.STRATEGIES`, skips disabled entries (logged), and
  defers to `start_strategy()` for each enabled one.
- `start_strategy(name)` looks up config + `REGISTRY`, instantiates
  `cls(ctx, cfg["params"])`, starts it on a `daemon` thread named `strat-{name}`, and
  records both in the dicts. Returns `False` (logged) if already running, or missing a
  config / registry entry. Re-instantiates fresh each call, so a stopped strategy can
  be restarted cleanly despite the base's one-shot `_stop` Event.
- `stop_strategy(name)` signals that one strategy via `stop()`, joins its thread, and
  drops it from both dicts.
- `shutdown()` preserves Step 1's ordering: `stop()` **all** strategies first, then
  `join(timeout=10)` each — one signal reaches every strategy before any join blocks.
- `status()` returns `{name: "running"|"stopped"}` from each thread's `is_alive()`.

### `main.py`
- Dropped the start/join loop and the `(strat, thread)` bookkeeping; those now live in
  `Engine`. `main()` is now: build context, `Engine(ctx)`, `engine.start()`, block on a
  `SIGINT`/`SIGTERM` Event, then `engine.shutdown()`.

## Verifying

```bash
python main.py
```

- Expected: **identical** behavior to Step 1 — `[strat-rsi_buy]` and `[strat-heartbeat]`
  log lines interleave; a single Ctrl-C prints `shutting down...` then `stopped` for both.
- New capability: from a REPL you can drive strategies individually, e.g.

  ```python
  from engine import Engine
  from main import build_context
  eng = Engine(build_context()); eng.start()
  eng.stop_strategy("rsi_buy")   # rsi_buy stops, heartbeat keeps ticking
  eng.status()                   # {'heartbeat': 'running'}
  eng.start_strategy("rsi_buy")  # back up again
  ```

  (A full run still needs `.env` keys, since `build_context()` builds the real
  Supabase/Alpaca clients.)

## Notes for later steps

- `Engine` is deliberately strategy-only: **no scheduler/watchdog yet** (those are later
  steps). Keeping it minimal here makes each later subsystem a small addition that plugs
  into this seam.
- The admin API (Step ?) will call `start_strategy` / `stop_strategy` / `status` directly.
