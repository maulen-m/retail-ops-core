"""
TASK-044: Centralized Logging Configuration

Provides consistent logging across all scripts.
- Rotating file logs (10MB max, keep 5)
- Console output (INFO level)
- Separate error log
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path = None,
    app_name: str = 'inventory_system'
) -> logging.Logger:
    """
    Configure centralized logging.

    Call at start of every script:
        from core.logging_config import setup_logging
        logger = setup_logging()

    Args:
        level: Log level (default: INFO)
        log_dir: Directory for log files (default: project_root/logs)
        app_name: Application name for logger

    Returns:
        Configured logger instance
    """
    # Determine log directory
    if log_dir is None:
        project_root = Path(__file__).parent.parent
        log_dir = project_root / 'logs'

    log_dir.mkdir(parents=True, exist_ok=True)

    # Get or create logger
    logger = logging.getLogger(app_name)

    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Log format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler - rotating (10MB max, keep 5)
    file_handler = RotatingFileHandler(
        log_dir / 'app.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Error file handler - separate file for errors
    error_handler = RotatingFileHandler(
        log_dir / 'errors.log',
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a child logger for a module.

    Usage in any module:
        from core.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance
    """
    base_logger = logging.getLogger('inventory_system')

    if name:
        return base_logger.getChild(name)

    return base_logger


def log_function_call(logger: logging.Logger):
    """
    Decorator to log function entry/exit.

    Usage:
        @log_function_call(logger)
        def my_function():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.debug(f"Entering {func.__name__}")
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Exiting {func.__name__}")
                return result
            except Exception as e:
                logger.exception(f"Exception in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator


class LogContext:
    """
    Context manager for structured logging.

    Usage:
        with LogContext(logger, "Processing SKU", sku_key=sku):
            # do work
            # automatically logs start/end/duration
    """

    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None

    def __enter__(self):
        import time
        self.start_time = time.time()
        ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
        self.logger.info(f"START: {self.operation} ({ctx_str})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.time() - self.start_time
        ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())

        if exc_type:
            self.logger.error(
                f"FAILED: {self.operation} ({ctx_str}) after {duration:.2f}s - {exc_val}"
            )
        else:
            self.logger.info(
                f"DONE: {self.operation} ({ctx_str}) in {duration:.2f}s"
            )

        return False  # Don't suppress exceptions
