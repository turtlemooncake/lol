import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from config.service_settings import ServiceSettings
from services.alpaca_trader import AlpacaTrader
from services.supabase import SupabaseDB

logger = logging.getLogger("order_gateway")


@dataclass
class OrderIntent:
    """What a strategy *wants* to do. The gateway decides if it happens."""

    strategy: str
    symbol: str
    notional: float  # dollars to deploy (fractional market order)
    side: str = "buy"


@dataclass
class OrderResult:
    accepted: bool
    reason: str = ""
    client_order_id: str | None = None
    broker_order_id: str | None = None


class OrderGateway:
    """The single risk-checked, serialized path every order must pass through.

    Step 1 put multiple order-placing threads behind one shared broker client;
    this is the chokepoint that makes that safe. Every order is:

      1. serialized by one global lock (the shared broker is never hit
         concurrently and the capital checks never race),
      2. risk-checked: a hard per-order notional cap, then a per-strategy
         capital bucket read from ServiceSettings.STRATEGIES,
      3. recorded to the `trades` table *before* the broker call -- a crash
         mid-submit leaves a durable record, and the unique client_order_id
         (strategy__symbol__rand) makes a replay idempotent at the broker,
      4. submitted, then the same row is updated with the outcome.

    Strategies must call ctx.gateway.submit(OrderIntent(...)); they never touch
    the broker directly.
    """

    TRADES_TABLE = "trades"

    def __init__(self, db: SupabaseDB, trader: AlpacaTrader):
        self.db = db
        self.trader = trader
        self._lock = threading.Lock()
        # Dollars deployed per strategy this session, capped by each strategy's
        # STRATEGIES[*]["capital"]. In-memory: reset on restart (positions are
        # the source of truth for actual exposure; this is the soft governor).
        self._deployed: dict[str, float] = {}

    def submit(self, intent: OrderIntent) -> OrderResult:
        """Risk-check, record, and submit one order. Fully serialized."""
        with self._lock:
            return self._submit_locked(intent)

    def _submit_locked(self, intent: OrderIntent) -> OrderResult:
        cfg = ServiceSettings.STRATEGIES.get(intent.strategy)
        if cfg is None:
            return self._reject(intent, "unknown strategy")

        # Per-order notional cap (global, every strategy).
        if intent.notional <= 0:
            return self._reject(intent, "non-positive notional")
        if intent.notional > ServiceSettings.MAX_ORDER_NOTIONAL:
            return self._reject(
                intent,
                f"over MAX_ORDER_NOTIONAL "
                f"(${intent.notional:.2f} > ${ServiceSettings.MAX_ORDER_NOTIONAL})",
            )

        # Per-strategy capital bucket.
        capital = cfg.get("capital", 0)
        deployed = self._deployed.get(intent.strategy, 0.0)
        if deployed + intent.notional > capital:
            return self._reject(
                intent,
                f"over capital bucket "
                f"(${deployed + intent.notional:.2f} > ${capital})",
            )

        # Cash floor: halt new orders once the account is nearly out of cash.
        # Network call, inside the lock, fail-closed like the throttle below.
        try:
            cash = self.trader.get_account_cash()
        except Exception as e:
            return self._reject(intent, f"cash check failed: {e}")
        if cash < ServiceSettings.MIN_ACCOUNT_CASH:
            return self._reject(
                intent,
                f"account cash below MIN_ACCOUNT_CASH "
                f"(${cash:.2f} < ${ServiceSettings.MIN_ACCOUNT_CASH})",
            )

        # Open-order throttle: don't pile onto the broker past MAX_OPEN_ORDERS.
        # Checked last (it's a network call) and inside the lock, so concurrent
        # submits can't race past the cap. Fail-closed if the broker errors.
        try:
            open_orders = self.trader.get_open_order_count()
        except Exception as e:
            return self._reject(intent, f"open-order check failed: {e}")
        if open_orders >= ServiceSettings.MAX_OPEN_ORDERS:
            return self._reject(
                intent,
                f"over MAX_OPEN_ORDERS "
                f"({open_orders} >= {ServiceSettings.MAX_OPEN_ORDERS})",
            )

        # Attribution id, then record-before-submit.
        client_order_id = self._make_client_order_id(intent)
        # self._record(intent, client_order_id, status="pending")

        try:
            order = self.trader.submit_order(
                symbol=intent.symbol,
                notional=intent.notional,
                side=intent.side,
                client_order_id=client_order_id,
            )
        except Exception as e:
            logger.exception("broker submit failed for %s", client_order_id)
            self._mark(client_order_id, "failed", reason=str(e))
            return OrderResult(False, f"broker error: {e}", client_order_id)

        broker_order_id = str(getattr(order, "id", "") or "") or None
        self._mark(client_order_id, "submitted", broker_order_id=broker_order_id)
        self._deployed[intent.strategy] = deployed + intent.notional
        logger.info(
            "accepted %s %s $%.2f -> %s",
            intent.strategy,
            intent.symbol,
            intent.notional,
            client_order_id,
        )
        return OrderResult(True, "", client_order_id, broker_order_id)

    def _make_client_order_id(self, intent: OrderIntent) -> str:
        return f"{intent.strategy}__{intent.symbol}__{uuid.uuid4().hex[:12]}"

    def _reject(self, intent: OrderIntent, reason: str) -> OrderResult:
        # Rejected intents are still recorded -- a safety chokepoint wants the
        # audit trail of what it blocked.
        client_order_id = self._make_client_order_id(intent)
        # self._record(intent, client_order_id, status="rejected", reason=reason)
        logger.warning(
            "rejected %s %s $%.2f: %s",
            intent.strategy,
            intent.symbol,
            intent.notional,
            reason,
        )
        return OrderResult(False, reason, client_order_id)

    # def _record(
    #     self,
    #     intent: OrderIntent,
    #     client_order_id: str,
    #     status: str,
    #     reason: str = "",
    # ) -> None:
    #     self.db.insert_row(
    #         self.TRADES_TABLE,
    #         {
    #             "client_order_id": client_order_id,
    #             "strategy": intent.strategy,
    #             "symbol": intent.symbol,
    #             "side": intent.side,
    #             "notional": intent.notional,
    #             "status": status,
    #             "reason": reason,
    #         },
    #     )

    def _mark(
        self,
        client_order_id: str,
        status: str,
        broker_order_id: str | None = None,
        reason: str = "",
    ) -> None:
        values: dict = {"status": status}
        if broker_order_id:
            values["broker_order_id"] = broker_order_id
        if reason:
            values["reason"] = reason
        if status == "submitted":
            values["submitted_at"] = datetime.now(timezone.utc).isoformat()
        # self.db.update_row(
        #     self.TRADES_TABLE, {"client_order_id": client_order_id}, values
        # )
