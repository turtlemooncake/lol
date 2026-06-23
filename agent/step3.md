# Step 3 — OrderGateway (the safety chokepoint)

**Goal:** every order goes through **one** risk-checked, attributed, serialized path.
The moment Step 1 put multiple order-placing threads behind a single shared broker
client, this became necessary — land it before `loop_once()` does anything real.

## Files touched

| File | Change |
|------|--------|
| `services/order_gateway.py` | New. `OrderGateway` + `OrderIntent`/`OrderResult` dataclasses |
| `services/alpaca_trader.py` | New `submit_order()` + `get_open_order_count()` + `get_account_cash()` |
| `services/supabase.py` | New `insert_row()` / `update_row()` (generic single-row writes) |
| `config/context.py` | Added optional `gateway` field |
| `main.py` | `build_context()` wires the gateway from the shared `db` + `alpacaTrader` |
| `strategies/rsi_buy.py` | `loop_once()` now emits an `OrderIntent` per oversold name via `self.ctx.gateway.submit(...)` |
| `config/service_settings.py` | Added `order_notional` to `rsi_buy` params; added `MAX_OPEN_ORDERS` + `MIN_ACCOUNT_CASH` |
| `db/trades.sql` | New Supabase `trades` table (the gateway's audit log) |

## What changed

### `services/order_gateway.py` (new)
- `OrderIntent(strategy, symbol, notional, side="buy")` — what a strategy *wants*.
- `OrderResult(accepted, reason, client_order_id, broker_order_id)` — what happened.
- `OrderGateway(db, trader)` is the single path to the broker:
  - **One `threading.Lock`** serializes every `submit()` — the shared broker client is
    never hit concurrently and the capital checks never race.
  - **Risk checks**, cheapest first: non-positive notional → reject; notional >
    `MAX_ORDER_NOTIONAL` → reject; `deployed[strategy] + notional > capital` → reject; then
    two broker-state checks — account cash `< MIN_ACCOUNT_CASH` → reject (the cash floor),
    and open broker orders `>= MAX_OPEN_ORDERS` → reject (the throttle).
    Per-strategy capital is read from `STRATEGIES[name]["capital"]`; `deployed` is tracked
    in-memory per strategy this session.
  - The cash-floor and open-order checks are the network calls among the checks, so they run
    **last** and **inside the lock** (concurrent submits can't race past a cap). Both **fail
    closed**: if the broker errors on either query, the order is rejected, not submitted
    blind. Each rejection is logged via `_reject` (`rejected <strat> <sym> $<n>: <reason>`).
    Note: a strategy's just-accepted order isn't reflected in the open count until Alpaca
    reports it, so a tight burst can exceed the cap by a small margin — fine for a throttle.
  - **Attribution**: `client_order_id = f"{strategy}__{symbol}__{rand}"`.
  - **Record-before-submit** (restart idempotency): the row is inserted as `pending`
    *before* the broker call, so a crash mid-submit leaves a durable record, and the unique
    `client_order_id` makes a replay idempotent at Alpaca. After submit the same row is
    updated to `submitted` (+ broker order id) or `failed` (+ reason).
  - Rejected intents are recorded too (`status='rejected'`) — a safety chokepoint wants the
    audit trail of what it blocked.

### `services/alpaca_trader.py`
- `submit_order(symbol, notional, side, client_order_id)` builds a `MarketOrderRequest`
  (`notional`, `TimeInForce.DAY` — required for notional orders) and submits it. Called
  **only** by the gateway.
- `get_open_order_count()` returns how many orders are currently open at the broker
  (`GetOrdersRequest(status=QueryOrderStatus.OPEN)`), for the gateway's throttle.
- `get_account_cash()` returns the account's settled cash (`get_account().cash` as a float),
  for the gateway's cash floor.

### `services/supabase.py`
- `insert_row(table, row)` and `update_row(table, match, values)` — the generic writes the
  gateway uses (the existing `upsert_rows` is keyed to the universe's conflict target).

### `config/context.py` + `main.py`
- `Context` gains an optional `gateway` field (default `None`). It's built *after* the
  services it wraps, so `build_context()` constructs `db` + `alpacaTrader` first, then sets
  `ctx.gateway = OrderGateway(db, alpacaTrader)`.

### `strategies/rsi_buy.py`
- `setup()` reads `order_notional` (default `$50`).
- `loop_once()` no longer just stashes `self.oversold`; it calls `_place_orders()`, which
  submits one `OrderIntent` per oversold name through `self.ctx.gateway`. Strategies
  **never** touch the broker directly.

### `config/service_settings.py`
- Added `"order_notional": 50.0` to `rsi_buy` params (must be `<= MAX_ORDER_NOTIONAL`).
- Added `MAX_OPEN_ORDERS` — global cap on open broker orders the gateway will allow.
- Added `MIN_ACCOUNT_CASH` — the gateway halts new orders once account cash drops below this.

### `db/trades.sql` (new)
- `trades` table: `client_order_id` (unique), `strategy`, `symbol`, `side`, `notional`,
  `status` (`pending → submitted | failed`, or `rejected`), `reason`, `broker_order_id`,
  `created_at`, `submitted_at`, plus indexes on `strategy` and `created_at`.

## Verifying

Run this SQL once in Supabase (`db/trades.sql`) to create the table, then:

- **Over-cap intent is rejected**: `gateway.submit(OrderIntent("rsi_buy", "AAA", 999))`
  returns `accepted=False` with reason `over MAX_ORDER_NOTIONAL` and never reaches the broker.
- **Accepted intent lands in `trades`**: `gateway.submit(OrderIntent("rsi_buy", "MSFT", 50))`
  returns `accepted=True`; the row in `trades` has `status='submitted'`, a `broker_order_id`,
  and a `client_order_id` of the form `rsi_buy__MSFT__<rand>`.
- **Capital bucket caps total exposure**: with `rsi_buy` capital `$1000` and `$50`/order, the
  21st accepted order is rejected (`over capital bucket`).
- **Open-order throttle**: with a fake trader reporting `MAX_OPEN_ORDERS` open orders, the next
  intent is rejected (`over MAX_OPEN_ORDERS`) and the broker is never hit; if the count query
  raises, the intent is rejected fail-closed (`open-order check failed: ...`).
- **Cash floor**: with a fake trader reporting cash `< MIN_ACCOUNT_CASH`, the next intent is
  rejected (`account cash below MIN_ACCOUNT_CASH`) and logged, broker never hit; if the cash
  query raises, the intent is rejected fail-closed (`cash check failed: ...`).

## Notes for later steps

- `deployed` is in-memory (resets on restart). Actual exposure lives in broker positions;
  a later reconciliation step can rebuild buckets from positions / `trades` at boot.
- `MAX_DAILY_LOSS` (in settings) is **not** enforced yet — that's the engine-level pause,
  a later step. The gateway only governs per-order notional + per-strategy capital here.
- The gateway is the seam the admin API and watchdog will read trade state from.
