import os
import logging
from logging.handlers import RotatingFileHandler

# Base directories
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

# Standard Logger configuration
logger = logging.getLogger("AIJobHunter")
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] - %(message)s'
)

# Stream Handler (console)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Rotating File Handler (general log)
general_log_path = os.path.join(LOG_DIR, "app.log")
file_handler = RotatingFileHandler(general_log_path, maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Error log Handler
error_log_path = os.path.join(LOG_DIR, "error.log")
error_file_handler = RotatingFileHandler(error_log_path, maxBytes=5*1024*1024, backupCount=5)
error_file_handler.setLevel(logging.ERROR)
error_file_handler.setFormatter(formatter)
logger.addHandler(error_file_handler)

# Performance Logger
perf_logger = logging.getLogger("AIJobHunterPerf")
perf_logger.setLevel(logging.INFO)
perf_log_path = os.path.join(LOG_DIR, "performance.log")
perf_handler = RotatingFileHandler(perf_log_path, maxBytes=5*1024*1024, backupCount=3)
perf_handler.setFormatter(logging.Formatter('[%(asctime)s] - %(message)s'))
perf_logger.addHandler(perf_handler)

# Database Logging helper (lazy import to prevent circular dependency)
def log_to_db(level: str, message: str, module: str):
    """
    Directly logs a message to the PostgreSQL logs table.
    Fails gracefully if the DB is unavailable.
    """
    from sqlalchemy import text
    try:
        from scripts.database import get_db_session
        session = next(get_db_session())
        if session:
            session.execute(
                text("INSERT INTO logs (level, message, module) VALUES (:level, :message, :module)"),
                {"level": level, "message": message, "module": module}
            )
            session.commit()
            session.close()
    except Exception as e:
        # Fallback only to logger, do not loop
        logger.error(f"Failed to log to database: {e}")

def log_info(message: str, module: str = "System"):
    logger.info(f"[{module}] {message}")
    log_to_db("INFO", message, module)

def log_error(message: str, module: str = "System"):
    logger.error(f"[{module}] {message}")
    log_to_db("ERROR", message, module)

def log_warning(message: str, module: str = "System"):
    logger.warning(f"[{module}] {message}")
    log_to_db("WARNING", message, module)

def log_performance(message: str):
    perf_logger.info(message)
    # Also save performance to DB
    log_to_db("PERF", message, "Performance")
