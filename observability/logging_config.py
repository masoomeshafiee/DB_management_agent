from __future__ import annotations

import logging
import logging.config
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = Path("logs")

def config_logging(log_dir:Path | str=DEFAULT_LOG_DIR, level: str="INFO") -> None:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)


    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    max_bytes = 5 * 1024 * 1024  # 5 MB per file
    backup_count = 3

    def rotating_handler(filename: str, handler_level: str) -> dict:
        return {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "standard",
            "level": handler_level,
            "filename": str(log_dir / filename),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": fmt, "datefmt": datefmt},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": level,
            },
            "app_file": rotating_handler("app.log", level),
            "audit_file": rotating_handler("audit.log", level),
            "adk_file": rotating_handler("adk.log", level),
            "error_file": rotating_handler("error.log", "WARNING"),
        },
        "loggers": {
            # Explicit audit trail logger (opt in with logging.getLogger("db_management_agent.audit"))
            "db_management_agent.audit": {
                "handlers": ["console", "audit_file", "error_file"],
                "level": level,
                "propagate": False,
            },

            # ADK framework logs, isolated from app logs (tune level independently if you want).
            # The installed google-adk / google-genai packages log under "google_adk.*" and
            # "google_genai.*" (underscore), not "google.adk" (dot) — match the real names.
            "google_adk": {
                "handlers": ["console", "adk_file", "error_file"],
                "level": level,
                "propagate": False,
            },
            "google_genai": {
                "handlers": ["console", "adk_file", "error_file"],
                "level": level,
                "propagate": False,
            },
        },
        # Every module calls logging.getLogger(__name__) and propagates here by default.
        "root": {"handlers": ["console", "app_file", "error_file"], "level": level},
    }

    logging.config.dictConfig(config)

