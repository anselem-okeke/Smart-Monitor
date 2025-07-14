import logging
import pathlib

LOG_DIR  = pathlib.Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGFILE = LOG_DIR / "network_recovery.log"

_logger = logging.getLogger("net-recovery")
if not _logger.handlers:                      # init only once
    h = logging.FileHandler(LOGFILE, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
    h.setFormatter(fmt)
    _logger.addHandler(h)
    _logger.setLevel(logging.INFO)

def net_log(level, msg):
    getattr(_logger, level.lower())(msg)