from strategies.heartbeat import Heartbeat
from strategies.rsi_buy import RsiBuy

REGISTRY = {
    RsiBuy.name: RsiBuy,
    Heartbeat.name: Heartbeat,
}
