from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from src.clients.alpaca_client import TRADING_CLIENT


def get_all_assets() -> list[dict]:
    request = GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY,
        status=AssetStatus.ACTIVE,
    )

    try:
        assets = TRADING_CLIENT.get_all_assets(request)
        return assets
    except Exception as e:
        print(f"Failed Alpaca get_all_assets: {e}")
        return []
