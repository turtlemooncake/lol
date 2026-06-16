import threading
from alpaca.trading.client import TradingClient
from config.service_settings import ServiceSettings
from alpaca.trading import Asset
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus


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

            filtered_assets.append(asset)

        return filtered_assets

    def get_all_filtered_assets(self) -> list[Asset]:
        all_assets = self._get_all_assets()
        filtered_assets = self._filter_all_assets(all_assets)

        return filtered_assets
