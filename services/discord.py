import logging

import requests

from config.service_settings import ServiceSettings

logger = logging.getLogger("discord")


def send_discord_message(content: str) -> None:
    """Post a message to the configured Discord webhook.

    Fail-soft: notifications are a side channel, never part of order flow. A
    missing webhook URL is a no-op, and any network/HTTP error only logs -- it
    must never raise into a strategy's loop or the order path.
    """
    url = ServiceSettings.DISCORD_WEBHOOK_URL
    if not url:
        return
    try:
        resp = requests.post(url, json={"content": content}, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("failed to send discord message: %s", e)
