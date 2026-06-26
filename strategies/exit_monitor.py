import logging
from datetime import datetime, timezone

from services.discord import send_discord_message
from strategies.base import Strategy
from util import parse_ts

log = logging.getLogger("strategy.exit_monitor")


class ExitMonitor(Strategy):
    """Periodically reviews open positions and closes winners / stale holds.

    Either rule triggers a full close of a position:
      * take-profit -- unrealized P/L >= take_profit_pct (e.g. +3%)
      * time-stop   -- held >= max_hold_days calendar days

    Closing liquidates the whole position via the broker directly rather than
    through the OrderGateway: the gateway governs *entries* (capital buckets,
    notional caps); an exit is risk-reducing and qty-based, so it isn't gated.
    Every close is announced to Discord (fail-soft).
    """

    name = "exit_monitor"
    # Closing a position needs a live market, so gate like any trading strategy.
    requires_market_open = True

    def setup(self) -> None:
        self.take_profit_pct = self.params.get("take_profit_pct", 0.03)
        self.max_hold_days = self.params.get("max_hold_days", 10)

    def loop_once(self) -> None:
        positions = self.ctx.alpacaTrader.get_all_positions()
        if not positions:
            log.info("no open positions")
            return

        for pos in positions:
            reason = self._exit_reason(pos)
            if reason:
                self._close(pos, reason)

    def _exit_reason(self, pos) -> str | None:
        """The reason to close `pos`, or None to keep holding."""
        symbol = pos.symbol

        # 1. Take-profit. unrealized_plpc is a fraction (0.0325 == +3.25%).
        plpc = self._plpc(pos)
        if plpc >= self.take_profit_pct:
            return f"take-profit (+{plpc * 100:.2f}% >= +{self.take_profit_pct * 100:.0f}%)"

        # 2. Time-stop. Skip silently if there's no recorded entry to age from.
        open_time = parse_ts(self.ctx.db.last_entry_time(symbol))
        if open_time is not None:
            days_held = (datetime.now(timezone.utc) - open_time).total_seconds() / 86400
            if days_held >= self.max_hold_days:
                return f"time-stop ({days_held:.1f}d >= {self.max_hold_days}d)"

        log.info("%s held, no exit (plpc=%+.2f%%)", symbol, plpc * 100)
        return None

    def _close(self, pos, reason: str) -> None:
        symbol = pos.symbol
        log.info("closing %s: %s", symbol, reason)
        order = self.ctx.alpacaTrader.close_position(symbol)
        if order is None:
            log.warning("close failed for %s - will retry next tick", symbol)
            return

        pl = float(pos.unrealized_pl) if pos.unrealized_pl is not None else 0.0
        send_discord_message(
            f"💰 **Position closed** — `{symbol}` ({reason})\n"
            f"qty: `{pos.qty}` · unrealized P/L: ${pl:.2f} ({self._plpc(pos) * 100:+.2f}%)"
        )

    @staticmethod
    def _plpc(pos) -> float:
        """Unrealized P/L percent as a fraction; 0.0 if the broker omits it."""
        return float(pos.unrealized_plpc) if pos.unrealized_plpc is not None else 0.0
