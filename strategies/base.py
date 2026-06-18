import logging
import time
import threading
from abc import ABC, abstractmethod

from config.context import Context

logger = logging.getLogger("strategy")


class Strategy(ABC):
    """Base class. Subclasses implement loop_once(); the base owns the loop."""

    name: str = "base"

    def __init__(self, ctx: Context, params: dict):
        self.ctx = ctx
        self.params = params
        self.poll_interval = params.get("poll_interval", 300)
        self.error_backoff = 30
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def setup(self) -> None:
        """One-time prep before the loop. Optional override."""

    def teardown(self) -> None:
        """Cleanup on stop. Optional override."""

    def stop(self) -> None:
        self._stop.set()

    @abstractmethod
    def loop_once(self) -> None:
        """One iteration. Raise freely — run() catches and logs."""

    def run(self) -> None:
        log = logging.getLogger(f"strategy.{self.name}")
        log.info("starting (poll every %ds)", self.poll_interval)

        try:
            self.setup()
        except Exception:
            log.exception("setup failed - strategy no run")
            return

        while not self._stop.is_set():
            try:
                self.loop_once()
            except Exception:
                log.exception("loop_once error - backing off %ds", self.error_backoff)
                self._stop.wait(self.error_backoff)
                continue
            self._stop.wait(self.poll_interval)

        try:
            self.teardown()
        finally:
            log.info("stopped")
