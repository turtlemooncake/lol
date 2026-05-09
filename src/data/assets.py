from alpaca.trading import Asset
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus
from src.clients.alpaca_client import TRADING_CLIENT


def _get_all_assets() -> list[Asset]:
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


def _filter_all_assets(assets: list[Asset]) -> list[Asset]:
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


def get_all_filtered_assets() -> list[Asset]:
    all_assets = _get_all_assets()
    filtered_assets = _filter_all_assets(all_assets)

    return filtered_assets
