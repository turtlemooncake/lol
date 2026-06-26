from strategies.exit_monitor import ExitMonitor
from strategies.heartbeat import Heartbeat
from strategies.rsi_buy import RsiBuy

REGISTRY = {
    RsiBuy.name: RsiBuy,
    ExitMonitor.name: ExitMonitor,
    Heartbeat.name: Heartbeat,
}
