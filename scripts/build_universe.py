import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.assets import get_all_filtered_assets
from src.data.candles import download_candle_bars


def main():
    start_time = time.time()

    # 1. Pull all assets and filter
    assets = get_all_filtered_assets()
    assets = assets[:10]

    # 2. Download Daily Bars
    download_candle_bars(assets)

    pass


if __name__ == "__main__":
    print("universe builder")
    main()
