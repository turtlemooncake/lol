from dataclasses import dataclass

from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.supabase import SupabaseDB


@dataclass
class Context:
    db: SupabaseDB
    alpacaData: AlpacaData
    alpacaTrader: AlpacaTrader
