import logging
import threading

from config.context import Context
from config.service_settings import ServiceSettings
from strategies import REGISTRY
from strategies.base import Strategy

logger = logging.getLogger("engine")


class Engine:
    """Owns strategy instances and their threads.

    Strategies can be started/stopped individually (start_strategy/stop_strategy)
    or all at once (start/shutdown). This is the seam the admin API plugs into.
    """

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.strategies: dict[str, Strategy] = {}
        self.threads: dict[str, threading.Thread] = {}

    def start(self) -> None:
        """Start every enabled strategy in config."""
        for name, cfg in ServiceSettings.STRATEGIES.items():
            if not cfg.get("enabled"):
                logger.info("strategy %s disabled - skipping", name)
                continue
            self.start_strategy(name)
        logger.info("started %d strategies", len(self.threads))

    def start_strategy(self, name: str) -> bool:
        """Instantiate and start one strategy on its own daemon thread."""
        if name in self.threads and self.threads[name].is_alive():
            logger.warning("strategy %s already running", name)
            return False
        cfg = ServiceSettings.STRATEGIES.get(name)
        if cfg is None:
            logger.warning("strategy %s has no config entry - skipping", name)
            return False
        cls = REGISTRY.get(name)
        if cls is None:
            logger.warning("strategy %s has no REGISTRY entry - skipping", name)
            return False

        strat = cls(self.ctx, cfg["params"])
        thread = threading.Thread(
            target=strat.run, name=f"strat-{name}", daemon=True
        )
        thread.start()
        self.strategies[name] = strat
        self.threads[name] = thread
        return True

    def stop_strategy(self, name: str, timeout: float = 10) -> bool:
        """Signal one strategy to stop and join its thread."""
        strat = self.strategies.get(name)
        if strat is None:
            logger.warning("strategy %s not running", name)
            return False
        strat.stop()
        thread = self.threads.get(name)
        if thread is not None:
            thread.join(timeout=timeout)
        self.strategies.pop(name, None)
        self.threads.pop(name, None)
        logger.info("strategy %s stopped", name)
        return True

    def shutdown(self, timeout: float = 10) -> None:
        """Stop all strategies first, then join — one signal before any join."""
        logger.info("shutting down...")
        for strat in self.strategies.values():
            strat.stop()
        for thread in self.threads.values():
            thread.join(timeout=timeout)
        self.strategies.clear()
        self.threads.clear()

    def status(self) -> dict[str, str]:
        """Map each known strategy to 'running' or 'stopped'."""
        return {
            name: "running" if thread.is_alive() else "stopped"
            for name, thread in self.threads.items()
        }
