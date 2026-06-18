import logging
import signal
import threading

from config.context import Context
from config.service_settings import ServiceSettings
from services.alpaca_data import AlpacaData
from services.alpaca_trader import AlpacaTrader
from services.supabase import SupabaseDB
from strategies import REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def build_context() -> Context:
    # Built once, shared by every strategy (only one for now).
    return Context(
        db=SupabaseDB(),
        alpacaData=AlpacaData(),
        alpacaTrader=AlpacaTrader(),
    )


def main() -> None:
    logger.info("Trading Engine yee haw")
    ctx = build_context()

    # Step 0: one strategy, one thread.
    params = ServiceSettings.STRATEGIES["rsi_buy"]["params"]
    strat = REGISTRY["rsi_buy"](ctx, params)
    thread = threading.Thread(target=strat.run, name="strat-rsi_buy", daemon=True)
    thread.start()

    # Main thread blocks here until Ctrl-C / SIGTERM.
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    shutdown.wait()

    logger.info("shutting down...")
    strat.stop()
    thread.join(timeout=10)


if __name__ == "__main__":
    main()
