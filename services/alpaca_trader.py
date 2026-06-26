import threading
from datetime import datetime
from alpaca.trading.client import TradingClient
from config.service_settings import ServiceSettings
from alpaca.common.enums import Sort
from alpaca.trading import Asset
from alpaca.trading.models import Position
from alpaca.trading.requests import (
    GetAssetsRequest,
    GetOrdersRequest,
    MarketOrderRequest,
)
from alpaca.trading.enums import (
    AssetClass,
    AssetStatus,
    OrderSide,
    QueryOrderStatus,
    TimeInForce,
)


class AlpacaTrader:
    def __init__(self):
        self._lock = threading.Lock()  # todo: remove if unused
        self._TRADER_CLIENT = TradingClient(
            ServiceSettings.ALPACA_API_KEY,
            ServiceSettings.ALPACA_SECRET_KEY,
            paper=ServiceSettings.ALPACA_PAPER,
        )

    def _get_all_assets(self) -> list[Asset]:
        request = GetAssetsRequest(
            asset_class=AssetClass.US_EQUITY,
            status=AssetStatus.ACTIVE,
        )

        try:
            assets = self._TRADER_CLIENT.get_all_assets(request)
            return assets
        except Exception as e:
            print(f"Failed Alpaca get_all_assets: {e}")
            return []

    def _is_bond_fund(self, asset: Asset) -> bool:
        name = (asset.name or "").lower()
        return any(
            keyword in name for keyword in ServiceSettings.BOND_FUND_NAME_KEYWORDS
        )

    def _filter_all_assets(self, assets: list[Asset]) -> list[Asset]:
        filtered_assets = []
        bad_assets = []
        for asset in assets:
            # not tradeable
            if not asset.tradable:
                continue
            # fractional shares
            if not asset.fractionable:
                bad_assets.append(asset)
                continue
            # bond / fixed-income funds
            if self._is_bond_fund(asset):
                bad_assets.append(asset)
                continue

            filtered_assets.append(asset)

        return filtered_assets

    def get_all_filtered_assets(self) -> list[Asset]:
        all_assets = self._get_all_assets()
        filtered_assets = self._filter_all_assets(all_assets)

        return filtered_assets

    def is_market_open(self) -> bool:
        """Whether the US equity market is open right now, per Alpaca's clock.

        Fail-closed: if the clock call errors we report closed, so a broker or
        network blip never lets a strategy trade blind. Strategies keep beating
        and sleeping while this returns False.
        """
        try:
            return bool(self._TRADER_CLIENT.get_clock().is_open)
        except Exception as e:
            print(f"Failed Alpaca is_market_open: {e}")
            return False

    def get_open_order_count(self) -> int:
        """Number of currently-open (unfilled/working) orders at the broker."""
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = self._TRADER_CLIENT.get_orders(request)
        return len(orders)

    def at_open_order_limit(self) -> bool:
        """Whether open broker orders are at/above MAX_OPEN_ORDERS.

        The single throttle predicate: the gateway calls it per-order so each new
        order stays under the cap, and rsi_buy calls it at the top of a poll to
        skip a whole scan when there's no headroom. Raises on a broker error --
        callers decide how to fail (the gateway rejects, the strategy backs off).
        """
        return self.get_open_order_count() >= ServiceSettings.MAX_OPEN_ORDERS

    def get_account_cash(self) -> float:
        """Settled cash balance on the account, in dollars."""
        account = self._TRADER_CLIENT.get_account()
        return float(account.cash)

    def submit_order(
        self, symbol: str, notional: float, side: str, client_order_id: str
    ):
        """Submit a fractional-notional market order.

        Called only by OrderGateway (which serializes + risk-checks). The
        client_order_id carries strategy/symbol attribution and makes a replay
        idempotent: Alpaca rejects a second order with the same id.
        """
        request = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide(side),
            time_in_force=TimeInForce.DAY,  # required for notional orders
            client_order_id=client_order_id,
        )
        return self._TRADER_CLIENT.submit_order(request)

    def holds_symbol(self, symbol: str) -> bool:
        """Whether we already have exposure to `symbol` -- an open position OR a
        working (unfilled) order.

        The gateway uses this to refuse stacking a second entry on a name we're
        already in. Checks open orders too so a still-pending buy from a previous
        tick counts (positions only appear once filled). Fail-closed: on error we
        report True, so a broker blip skips the buy rather than risking a double.
        """
        try:
            positions = self._TRADER_CLIENT.get_all_positions()
            if any(p.symbol == symbol for p in positions):
                return True
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            open_orders = self._TRADER_CLIENT.get_orders(request)
            return len(open_orders) > 0
        except Exception as e:
            print(f"Failed Alpaca holds_symbol for {symbol}: {e}")
            return True

    def get_all_positions(self) -> list[Position]:
        """All currently-open positions at the broker.

        Fail-soft: returns [] on error so the exit monitor simply finds nothing
        to act on this tick rather than crashing its loop.
        """
        try:
            return self._TRADER_CLIENT.get_all_positions()
        except Exception as e:
            print(f"Failed Alpaca get_all_positions: {e}")
            return []

    def get_position_open_time(self, symbol: str) -> datetime | None:
        """Best-effort time the current position in `symbol` was opened.

        Alpaca's Position carries no open date, so we reconstruct it from filled
        order history: walking oldest-to-newest, a filled SELL means the symbol
        went flat (reset), and the first filled BUY after that starts the current
        position. Returns None if it can't be determined -- the caller treats that
        as "age unknown" and skips the time-based exit.
        """
        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            symbols=[symbol],
            limit=500,
            direction=Sort.ASC,
        )
        try:
            orders = self._TRADER_CLIENT.get_orders(request)
        except Exception as e:
            print(f"Failed Alpaca get_position_open_time for {symbol}: {e}")
            return None

        open_time: datetime | None = None
        for order in orders:
            if order.filled_at is None:
                continue
            if order.side == OrderSide.SELL:
                open_time = None  # symbol went flat -- start of run resets
            elif order.side == OrderSide.BUY and open_time is None:
                open_time = order.filled_at
        return open_time

    def close_position(self, symbol: str):
        """Liquidate the entire position in `symbol` (market order, all qty).

        Fail-soft: returns the closing Order, or None on error so a broker blip
        doesn't crash the exit monitor -- it retries on the next tick.
        """
        try:
            return self._TRADER_CLIENT.close_position(symbol)
        except Exception as e:
            print(f"Failed Alpaca close_position for {symbol}: {e}")
            return None
