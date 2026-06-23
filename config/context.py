from dataclasses import dataclass

from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.order_gateway import OrderGateway
from services.supabase import SupabaseDB


@dataclass
class Context:
    db: SupabaseDB
    alpacaData: AlpacaData
    alpacaTrader: AlpacaTrader
    # The one risk-checked path to the broker. Built after the services it
    # wraps, so it's wired in by build_context() rather than required here.
    gateway: OrderGateway | None = None
