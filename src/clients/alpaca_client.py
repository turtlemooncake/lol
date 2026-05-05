# src/clients/alpaca_client.py
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER

# Alpaca: Trade Broker client, Historical Data client
TRADING_CLIENT = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=ALPACA_PAPER)
DATA_CLIENT = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
