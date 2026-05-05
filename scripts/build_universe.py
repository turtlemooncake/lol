import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.assets import get_all_assets


def main():
    start_time = time.time()

    # 1. Pull all tickers
    assets = get_all_assets()
    print(f"assets length {len(assets)}")

    pass


if __name__ == "__main__":
    print("universe builder")
    main()
