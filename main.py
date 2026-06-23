import logging
import signal
import threading

from config.context import Context
from engine import Engine
from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.order_gateway import OrderGateway
from services.supabase import SupabaseDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_context() -> Context:
    # Built once, shared by every strategy.
    db = SupabaseDB()
    alpacaTrader = AlpacaTrader()
    ctx = Context(
        db=db,
        alpacaData=AlpacaData(),
        alpacaTrader=alpacaTrader,
    )
    # Wired after the services it wraps; the single path orders flow through.
    ctx.gateway = OrderGateway(db=db, trader=alpacaTrader)
    return ctx


def main() -> None:
    logger.info("Trading Engine yee haw")
    ctx = build_context()

    engine = Engine(ctx)
    engine.start()

    # Main thread blocks here until Ctrl-C / SIGTERM, then tears everything down.
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    shutdown.wait()

    engine.shutdown()


if __name__ == "__main__":
    main()
