import json
import os
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

"""FileCache Work in Progress. Need idea of what the data looks first"""


class FileCache:
    def __init__(
        self, filepath: str = "cache_snapshot.json", max_age_hours: float = 12
    ):
        self.filepath = filepath
        self.max_age_hours = max_age_hours
        self._data: dict = {}
        self._last_snapshot = 0.0

    def load(self) -> dict | None:
        return {}

    def save(self, candle_data: dict) -> None:
        pass

    def should_snapshot(self, interval_seconds: int = 600) -> bool:
        """Check if it's time for period snapshot"""
        return (time.time() - self._last_snapshot) >= interval_seconds

    def clear(self) -> None:
        """Delete snapshot file"""
        if os.path.exists(self.filepath):
            os.remove(self.filepath)

        self._data = {}
