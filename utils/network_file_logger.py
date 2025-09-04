import logging
import pathlib
import socket

LOG_DIR  = pathlib.Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGFILE = LOG_DIR / "network_recovery.log"

_logger = logging.getLogger("net-recovery")

# ---- add a logger-level filter so EVERY record has 'host' before propagation
class _HostFilter(logging.Filter):
    _HOST = socket.gethostname()
    def filter(self, record):
        if not hasattr(record, "host"):
            record.host = self._HOST
        return True

_logger.addFilter(_HostFilter())

# keep propagation ON so these messages also appear in the root/console
_logger.propagate = True
_logger.setLevel(logging.INFO)

if not _logger.handlers:                      # init only once
    h = logging.FileHandler(LOGFILE, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
    h.setFormatter(fmt)
    _logger.addHandler(h)
    _logger.setLevel(logging.INFO)

def net_log(level, msg):
    getattr(_logger, level.lower())(msg)