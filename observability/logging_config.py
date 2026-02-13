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

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": fmt, "datefmt": datefmt},
        },
        "handlers": {
            "consol": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": level,
            },

            "app_file": { 
                "class": "logging.FileHandler",
                "formatter": "standard",
                "level": level,
                "filename": str(log_dir / "app.log"),
                "encoding": "utf-8",
            },
            "audit_file": {
                "class": "logging.FileHandler",
                "formatter": "standard",
                "level": level,
                "filename": str(log_dir / "audit.log"),
                "encoding": "utf-8",
            },

            "adk_file": {
                "class": "logging.FileHandler",
                "formatter": "standard",
                "level": level,
                "filename": str(log_dir / "adk.log"),
                "encoding": "utf-8",
            },

            "error_file": {
                "class": "logging.FileHandler",
                "formatter": "standard",
                "level": "WARNING",
                "filename": str(log_dir / "error.log"),
                "encoding": "utf-8",
            },

        },
        "loggers": {
            "DB_management_agent": {
                "handlers": ["console", "app_file", "error_file"],
                "level": level,
                "propagate": False,
            },

            # Where your plugin writes (use this logger name inside your plugin)
            "db_management_agent.audit": {
                "handlers": ["console", "audit_file", "error_file"],
                "level": level,
                "propagate": False,
            },

            # ADK framework logs (tune level independently if you want)
            "google.adk": {
                "handlers": ["console", "adk_file", "error_file"],
                "level": level,
                "propagate": False,
            },
        },
        # Fallback for anything else
        "root": {"handlers": ["console", "error_file"], "level": "WARNING"},
    }

    logging.config.dictConfig(config)

