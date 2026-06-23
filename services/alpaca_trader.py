import threading
from alpaca.trading.client import TradingClient
from config.service_settings import ServiceSettings
from alpaca.trading import Asset
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

    def get_open_order_count(self) -> int:
        """Number of currently-open (unfilled/working) orders at the broker."""
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = self._TRADER_CLIENT.get_orders(request)
        return len(orders)

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
