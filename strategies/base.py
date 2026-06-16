import logging
import time
from abc import ABC, abstractmethod

from config.context import Context

logger = logging.getLogger("strategy")


class Strategy(ABC):
    """
    Abstract class for setting up different strategies
    """

    name: str = "base"

    def __init__(self, ctx: Context, params: dict):
        self.ctx = ctx
        self.params = params
        self.poll_interval = params.get("poll_interval", 300)
        self.running = False
        self.error_backoff = 30

    def setup(self) -> None:
        pass
