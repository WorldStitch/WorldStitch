import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Resolve log directory relative to the project root, not the working
# directory, so logs always land in the same place regardless of where
# the app or server is launched from.
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"


class SessionLogHandler(logging.Handler):
    def __init__(self, capacity=5000):
        super().__init__()
        self.buffer = deque(maxlen=capacity)
        self.setFormatter(
            logging.Formatter(
                "[%(asctime)s][%(levelname)s][%(threadName)s] %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record):
        try:
            msg = self.format(record)
            self.buffer.append(msg)
        except Exception:
            pass

    def clear(self):
        self.buffer.clear()

    def get_log_text(self):
        return "\n".join(self.buffer)


APP_SESSION_LOG_HANDLER = SessionLogHandler()
APP_SESSION_LOG_HANDLER.setLevel(logging.INFO)

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("[%(asctime)s][%(levelname)s][%(threadName)s] %(message)s", "%Y-%m-%d %H:%M:%S")
)
file_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, APP_SESSION_LOG_HANDLER])
