# Step 7 — Exits, single-entry-per-name, durable trade ledger

**Goal:** close the loop on the buy-only system from Steps 1–6. Four pieces: an
**exit monitor** that takes profit / time-stops open positions and pages Discord,
a **one-position-per-name** guard so a strategy never stacks a second entry on a
symbol it already holds, **re-enabling the `trades` table** so every order the
gateway touches leaves a durable, auditable row, and a **shared open-order-limit
predicate** that lets `rsi_buy` skip a whole scan when there's no headroom.

## Files touched

| File | Change |
|------|--------|
| `strategies/exit_monitor.py` | **New** strategy: closes positions at +3% or after 10 days, announces to Discord |
| `strategies/__init__.py` | Register `ExitMonitor` in `REGISTRY` |
| `config/service_settings.py` | New `exit_monitor` entry in `STRATEGIES` (capital 0, poll 300s, +3% / 10d params) |
| `services/alpaca_trader.py` | New `get_all_positions()`, `get_position_open_time()`, `close_position()`, `holds_symbol()`, `at_open_order_limit()` |
| `services/order_gateway.py` | One-position-per-name reject (buys); re-enabled `_record`/`_mark`; `_reject(record=...)` flag; throttle uses `at_open_order_limit()` |
| `services/supabase.py` | Re-enabled `insert_row()` / `update_row()` |
| `strategies/rsi_buy.py` | Top-of-poll short-circuit: skip the scan when `at_open_order_limit()` |

## What changed

### Exit monitor

- **`strategies/exit_monitor.py`** — a normal `Strategy` subclass, so it inherits
  the Step 6 machinery for free: market-open gate (`requires_market_open = True`,
  since closing needs a live market), heartbeats, and watchdog coverage. Each
  tick it pulls open positions and closes any that hit **either** rule:
  - **take-profit**: `unrealized_plpc >= take_profit_pct` (default +3%)
  - **time-stop**: held `>= max_hold_days` calendar days (default 10)
- A close **liquidates the whole position via the broker directly**, *not*
  through the OrderGateway. The gateway governs *entries* (capital buckets,
  notional caps); an exit is risk-reducing and qty-based, so it isn't gated.
  Every close posts a 💰 Discord message (fail-soft) with symbol, reason, qty,
  and unrealized P/L.
- Registered in `strategies/__init__.py` and configured in `STRATEGIES` with
  `capital: 0` (exits don't draw from a capital bucket) and `poll_interval: 300`.

### Position helpers on the trader

All fail-soft, matching the trader's print-on-error style:

- **`get_all_positions()`** — open positions; `[]` on error (monitor finds
  nothing to do this tick rather than crashing).
- **`get_position_open_time(symbol)`** — Alpaca's `Position` carries no open
  date, so this reconstructs it from filled order history: walking
  oldest→newest, a filled SELL means the symbol went flat (reset) and the first
  filled BUY after that starts the current position. Returns `None` if it can't
  be determined → the monitor skips the *time-stop* for that name (take-profit
  still applies). Best-effort: it doesn't perfectly attribute scale-ins/partial
  fills.
- **`close_position(symbol)`** — full liquidation; `None` on error (retried next
  tick).
- **`holds_symbol(symbol)`** — true if we have an open position **or** a working
  (unfilled) order in the symbol. **Fail-closed**: reports `True` on error so a
  broker blip skips a buy rather than risking a double entry.

### One position per name

- In `OrderGateway._submit_locked`, **buys** for a symbol we already hold (or
  have a working order for) are rejected via `holds_symbol`. Checked inside the
  serialized lock alongside the other network checks; sells never hit it (and
  exits don't route through the gateway anyway).
- Checking *open orders* — not just filled positions — matters with a fast poll:
  a buy from a previous tick can still be pending (a position only appears once
  filled), and without this it would re-submit.
- Because the guard lives at the gateway chokepoint, the rule applies to **every
  strategy**, not just `rsi_buy`.

### Durable trade ledger (re-enabled)

- The `trades` DDL already existed in `sql/trades.sql`; Step 7 just uncomments
  the code that writes to it:
  - `supabase.py`: `insert_row()` / `update_row()`
  - `order_gateway.py`: `_record()` (record-before-submit) + its calls in
    `_submit_locked` (`pending`) and `_reject` (`rejected`), and `update_row` in
    `_mark` (`submitted` / `failed`).
- Now every intent writes a `pending` row **before** the broker call and updates
  to `submitted`/`failed`/`rejected` after — the audit/recovery ledger Step 6
  flagged as missing. Both DB methods stay fail-soft (log only), so a DB hiccup
  can't take down the order path.
- **Scoped-out noise**: the new one-position-per-name reject passes
  `record=False` to `_reject` (gated behind the `ALREADY_HELD_REASON` constant).
  `rsi_buy` re-scans the same oversold names every tick, so this rejection fires
  repeatedly for held names — expected gating, not an audit-worthy block. It's
  still **logged**, just not written to `trades`. Every other rejection still
  records.

### Open-order limit — one predicate, two callers

- **`AlpacaTrader.at_open_order_limit()`** is now the single throttle predicate:
  `get_open_order_count() >= MAX_OPEN_ORDERS`. It **raises** on a broker error;
  each caller decides how to fail.
- **Gateway** (`_submit_locked`): the per-order throttle calls it inside the
  serialized lock, still **fail-closed** (rejects on error). This is what
  actually enforces the cap, so every new order stays under the limit.
- **`rsi_buy`** (top of `loop_once`): if already at the limit, log and `return`
  *before* the universe fetch / candle download / RSI math — the gateway would
  reject every resulting order anyway, so the whole scan is wasted work. A broker
  error here propagates and `run()` backs off.
- The two reads happen at different times (a deliberate TOCTOU gap): the
  top-of-poll check is only an optimization to skip work; the gateway's locked
  per-order check is the real guarantee.

## Verifying

- **Take-profit**: with an open position above +3% unrealized, the monitor's
  next tick closes it and posts a Discord message tagged `take-profit`.
- **Time-stop**: a position opened ≥ 10 days ago closes on the next tick tagged
  `time-stop (… >= 10d)`. (If `get_position_open_time` can't reconstruct the
  open, the time-stop is skipped — take-profit still works.)
- **One per name**: hold a symbol, then let `rsi_buy` flag it oversold again. The
  gateway logs a `rejected … already holding symbol` line, submits nothing, and
  writes **no** `trades` row for it.
- **Trade ledger**: place a buy. A `pending` row appears in `trades` before the
  broker call, flips to `submitted` (with `broker_order_id`, `submitted_at`)
  after; a real rejection (e.g. over capital) writes a `rejected` row.
- **Open-order limit**: with `MAX_OPEN_ORDERS` working orders already at the
  broker, `rsi_buy`'s next tick logs `at MAX_OPEN_ORDERS (N) - skipping scan`
  and does no universe/candle work; any order that still reaches the gateway is
  rejected `at/over MAX_OPEN_ORDERS`.

## Notes for later steps

- Exits bypass the gateway by design. If a unified ledger of *exits* is wanted,
  route closes through a sell-aware gateway path (the gateway is buy/notional-
  shaped today) so they also land in `trades`.
- `get_position_open_time` is order-history best-effort. With the `trades` table
  now live, a future step could read the opening fill from our own ledger
  instead of reconstructing it from broker order history.
- `rsi_buy`'s `poll_interval` is back to the production 300s. The held-symbol
  guard and the top-of-poll open-order short-circuit both keep a tick cheap when
  there's nothing to do, but each is still a per-tick broker call.
