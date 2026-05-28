from config.settings import UNIVERSE_TABLE_NAME
from src.db.db import fetch_universe_rows


def main():
    print(f"We are starting the simple server loop now yee haw")

    # Fetch universe
    rows = fetch_universe_rows(UNIVERSE_TABLE_NAME)

    # revist cache stuff here

    # Fetch candles

    # print(rows[0]["symbol"])


if __name__ == "__main__":
    main()
