import sys
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data.assets import get_all_filtered_assets


def main():
    start_time = time.time()

    # 1. Pull all assets and filter
    assets = get_all_filtered_assets()

    # 2. Download Daily Bars

    pass


if __name__ == "__main__":
    print("universe builder")
    main()
